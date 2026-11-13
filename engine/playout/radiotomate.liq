# Radiotomate's Liquidsoap script
# --------------------------
# This file is part of Radiotomate - Copyright (C) 2025 Martin Kirchgessner

# we have a few thread.run(fast=false so let's raise the number of fast queues
settings.scheduler.fast_queues := 5

settings.autocue.amplify_aliases := ["replaygain_track_gain", "rg_track_gain"]

# uncomment to set liquidsoap to "debug"
# settings.log.level := 5

# can be useful to debug, too
# server.telnet()

SCHEDULER_URL = "http://127.0.0.1:6822"

INPUT_PORT = 6800
API_PORT = 6833
BIND_ADDRS = ["0.0.0.0"]

BLANK_MAX_DURATION = 1.
BLANK_THRESHOLD = -45.
# Music often has a quiet verse or fade longer than 1s at -45 dB; eating that
# ends the track and jumps to the next Auto-DJ request.
AUTODJ_BLANK_MAX = 10.
AUTODJ_BLANK_THRESHOLD = -60.
CARTS_BLANK_MAX = 10.
# Under this, a title of the Auto-DJ has not played: see `DELETE /live`.
AUTODJ_PLAYED_S = 0.5

############################ CONFIGURATION LOADING #############################

path_to_config = environment.get("RTCONFIG")
if path_to_config == "" then
  print("Please set RTCONFIG to the path of the config file")
  shutdown(code=1)
end

if environment.get("AUTORELOAD") != "" then
  file.watch(liquidsoap.script.path, restart)
end

let yaml.parse (conf:{
  playout_process_config:{
    input_name:string,
    input_min_buffer:float,
    input_max_buffer:float,
    token:string,
    start_sound:string,
    log_path:string?,
    relay_url:string?,
    outputs: [{
      driver:string,
      device:string?,
      encoder:string?,
      quality:float?,
      host:string?,
      port:float?,
      mount:string?,
      password:string?,
    }]?
  },
  metadata_log:{
    extra_fields:[string],
  },
}) = file.contents(path_to_config)

MD_FIELDS = [
  ('initial_uri', 'keep'),
  ('source_url', 'keep'),
  ('source', 'keep'),
  ('on_air', 'keep'),
  ('artist', 'keep'),
  ('title', 'keep'),
  ('album', 'keep'),
  ('radiotomate_sound_id', 'keep'),
  ('radiotomate_item_id', 'keep'),
  ('radiotomate_queue', 'keep'),
  ... list.map(fun (f) -> (f, 'keep'), conf.metadata_log.extra_fields ?? [])
]

settings.harbor.bind_addrs := BIND_ADDRS

if null.defined(conf.playout_process_config.log_path)
then
  log_path = null.get(conf.playout_process_config.log_path)
  settings.log.file.set(true)
  settings.log.file.path.set(log_path)
end


################################# TOOLING #####################################

def crash(message, code=1)
  print(message)
  if settings.log.file() then
    file.write(data=message, append=true, settings.log.file.path())
  end
  shutdown(code=code)
end

def post_to_radiotomate(endpoint, data)
  res = http.post("#{SCHEDULER_URL}#{endpoint}",
    headers=[
      ("Content-Type", "application/json; charset=UTF-8"),
      ("X-Auth-Token", conf.playout_process_config.token),
    ],
    data=json.stringify(data)
  )
  if res.status_code != 200
  then
    log(label="Warning", "Error while posting #{endpoint} to webapp: #{res} #{res.status_code} #{res.status_message}")
  end
  res
end


def http_log(req, res, next)
  # would be nice to have the request's host/IP - also errors in this function will block the response silently !
  started_at = time()
  next(req, res)
  spent = time() - started_at
  if req.method != 'GET' or (req.path != '/version' and req.path != '/health') then
    log(label="http", "#{req.method} #{req.path} #{res.status_code.current()} #{spent}")
  end
end
harbor.http.middleware.register(http_log)

def check_token(req, res, next)
  if req.method == "GET" and (req.path == "/health" or req.path == "/voiceover") then
    next(req, res)
  elsif req.headers["x-auth-token"] != conf.playout_process_config.token then
    res.status_code(401)
  else
    next(req, res)
  end
end
harbor.http.middleware.register(check_token)


############################### MUSIC ####################################

autodj_queue = request.queue(id="autodj_queue")

# Titles follow each other in a straight cut, as in the other queues. No
# `crossfade` (nor `cross`) around this queue: in Liquidsoap 2.4.5 and 2.4.6 it
# stops pulling the queue a few seconds into a title. The same 20 ms frame then
# airs in a loop, a loud buzz, while `remaining` stays put and nothing is
# logged. playout/tests/antenna.py plays this script and listens for it.
autodj = blank.eat(id="autodj",
  start_blank=false,
  max_blank=AUTODJ_BLANK_MAX,
  threshold=AUTODJ_BLANK_THRESHOLD,
  stereo( # If there's a mono file
    autodj_queue
  )
)

# this leaves 3 seconds for the scheduler process to push the first jingle,
# then should push the first music
autodj_queue.push(request.create(conf.playout_process_config.start_sound))

############################### JINGLES ########################################

jingles_queue = request.queue(id="jingles_queue")

jingles = blank.eat(id="jingles",
  start_blank=true,
  max_blank=BLANK_MAX_DURATION,
  threshold=BLANK_THRESHOLD,
  stereo( # If there's a mono file
    jingles_queue
  )
)

################################ EXTERNAL RELAY ################################

# Default URL only seeds the source: the scheduler's RELAY carts pass their own
# URL through POST /relay (relay.set_url). Configurable via
# playout_process_config.relay_url; the placeholder is never started by itself.
RELAY_DEFAULT_URL = conf.playout_process_config.relay_url ?? "http://127.0.0.1:1/relay-not-configured"
relay = input.http(id="relay", RELAY_DEFAULT_URL,
  start=false, max_buffer=30., self_sync=false)


################################ LIVE SHOWS ####################################

# stream_auth_function ensures incoming streams are authenticated against Radiotomate's users directory
# the encoder sends its account's username, and its encoder token as password (scheduler/harbor.py)
def stream_auth_function(login) =
  res = post_to_radiotomate("/can_stream", login)
  if res.status_code == 200 then
    log("Access granted to #{login.user}")
    true
  else
    log("Access denied to #{login.user}")
    false
  end
end

stream = input.harbor(
  id="stream",
  auth=stream_auth_function,
  buffer=conf.playout_process_config.input_min_buffer,
  max=conf.playout_process_config.input_max_buffer,
  port=INPUT_PORT,
  conf.playout_process_config.input_name
)

########################### CARTS QUEUE ################################

carts_queue = request.queue(id="carts_queue")

# sometimes recorded shows forget a blank in the end - make it at most 10 seconds
carts = blank.eat(id="carts",
  start_blank=true,
  max_blank=CARTS_BLANK_MAX,
  threshold=BLANK_THRESHOLD,
  stereo( # If there's a mono file
    carts_queue
  )
)

########################### SOUNDS THAT WAIT ###################################

# A sound pushed with `wait` goes at the end of the title on air, instead of
# cutting it: a jingle of the motif, the sound of a cut on the minute that waits
# for the end, a line of the desk at its turn. The scheduler pushes them in the
# last seconds of the title: in `jingles_queue` or `carts_queue`, they cut these
# seconds, which came back after them. Each kind has its own queue, which a
# fallback below only looks at when a track ends (`track_sensitive=true`).
# Never ask these two sources whether they are ready (`source.is_ready`): that
# loads their next request, which a flush can then no longer take back.
# playout/tests/antenna.py pushes a jingle and a sound of a cart that wait.
jingles_wait_queue = request.queue(id="jingles_wait_queue")

jingles_wait = blank.eat(id="jingles_wait",
  start_blank=true,
  max_blank=BLANK_MAX_DURATION,
  threshold=BLANK_THRESHOLD,
  stereo( # If there's a mono file
    jingles_wait_queue
  )
)

carts_wait_queue = request.queue(id="carts_wait_queue")

carts_wait = blank.eat(id="carts_wait",
  start_blank=true,
  max_blank=CARTS_BLANK_MAX,
  threshold=BLANK_THRESHOLD,
  stereo( # If there's a mono file
    carts_wait_queue
  )
)

########################### COMBINING SOURCES ##################################

current_source_id = ref("starting")

# Heartbeat `/live` must keep exposing stream | relay | carts | jingles | autodj.
# The inner fallback ids are `title_end_carts` and, in it, `jingles_then_autodj`;
# resolve them to the ready child.
def on_air_source_id(sid)
  if sid == "title_end_carts" or sid == "jingles_then_autodj" then
    if source.is_ready(jingles) then "jingles" else "autodj" end
  elsif sid == "carts" or sid == "stream" or sid == "relay" or sid == "jingles" then
    sid
  else
    "autodj"
  end
end

# Transitions are currently broken in LS 2.3 :/   https://github.com/savonet/liquidsoap/issues/4179
# One transition per child of `programs`, which names the child it leads to.
# Nothing else tells it there: the source a transition is given is a wrapper,
# `insert_initial_track_mark.N`, and the child the antenna leaves still says it
# is ready. Read from the wrapper, a live was "autodj", and never stopped the
# relay it cut: the relay came back after it.
# playout/tests/antenna.py cuts a title with a relay, then with a live.
def crossfade_3s(sid)
  fun (_, b) -> begin
    current_source_id := on_air_source_id(sid)

    # if an input stream is on air, stop downloading from the relay
    if current_source_id() == "stream" then
      relay.stop()
    end

    b
  end
end

def mark_jingles_on_air(_, b)
  current_source_id := "jingles"
  b
end

def mark_autodj_on_air(_, b)
  current_source_id := "autodj"
  b
end

# A jingle that waits goes when the title of the Auto-DJ ends.
title_end_jingles = fallback([jingles_wait, autodj],
  track_sensitive=true,
  replay_metadata=true,
  id="title_end_jingles")

# Jingles still cut Auto-DJ, never live / relay / a cart already on air.
jingles_then_autodj = fallback([jingles, title_end_jingles],
  transitions=[mark_jingles_on_air, mark_autodj_on_air],
  track_sensitive=false,
  replay_metadata=true,
  id="jingles_then_autodj")

# A sound of a cart that waits goes when the title, or the jingle, on air ends.
title_end_carts = fallback([carts_wait, jingles_then_autodj],
  track_sensitive=true,
  replay_metadata=true,
  id="title_end_carts")

# Live takes the antenna as soon as the harbor buffer is ready.
# The final `blank()` keeps `programs` a safe source.
programs = fallback([stream, relay, carts, title_end_carts, blank()],
  transitions=[
    crossfade_3s("stream"),
    crossfade_3s("relay"),
    crossfade_3s("carts"),
    crossfade_3s("title_end_carts"),
    crossfade_3s("blank")
  ],
  track_sensitive=false,
  replay_metadata=true,
  id="programs")

# The child a fallback plays, by its id: "" when it plays none.
def selected_id(f) =
  s = f.selected()
  if null.defined(s) then source.id(null.get(s)) else "" end
end

# The queue on air: stream | relay | carts | carts_wait | jingles | jingles_wait
# | autodj, read in what each fallback has selected. `current_source_id` does
# not tell it: only the transitions set it, and the fallbacks of the sounds that
# wait have none. Read from the wrapper Liquidsoap 2.4 hands a transition,
# `insert_initial_track_mark.N`, it announced a cart, a live and a relay as
# "autodj", with the remaining time of the title they had cut, which waits. Nor
# does `source.is_ready`: a sound that waits is ready long before it plays.
# playout/tests/antenna.py cuts a title with a sound of the carts queue, then
# with a relay and a live.
def on_air_queue() =
  top = selected_id(programs)
  if top == "stream" or top == "relay" or top == "carts" then
    top
  elsif top != "title_end_carts" then
    # Nothing plays.
    "autodj"
  elsif selected_id(title_end_carts) == "carts_wait" then
    "carts_wait"
  elsif selected_id(jingles_then_autodj) == "jingles" then
    "jingles"
  elsif selected_id(title_end_jingles) == "jingles_wait" then
    "jingles_wait"
  else
    "autodj"
  end
end

# The source on air, for the heartbeat and `/health`: a sound that waited is a
# jingle or a sound of a cart as any other.
def on_air_source() =
  on_air = on_air_queue()
  if on_air == "carts_wait" then
    "carts"
  elsif on_air == "jingles_wait" then
    "jingles"
  else
    on_air
  end
end


settings.lufs.integrated_metadata := "rg_track_gain"
bed = normalize_track_gain(programs)

def post_to_log(md)
  log(label="replaygain", md["rg_track_gain"])
end

bed.on_metadata(synchronous=false, post_to_log)

############################ VOICEOVER (micro Hub) #############################

VOICEOVER_DUCK = 0.18
VOICEOVER_RESTORE_S = 15.0
voiceover_gain = ref(1.0)
voiceover_on = ref(false)
voiceover_fade = ref(1.2)
voiceover_ramp = ref(0)
voiceover_remaining = ref(0.)

def clamp_fade(x) =
  max(0.4, min(4.0, x))
end

def finite_seconds(x) =
  if x > 100000. then 0. else max(0., x) end
end

# The exact length of a title the scheduler pushes, 0. when unknown. ffmpeg,
# which decodes the files, estimates the length of an MP3 from the bitrate of
# its first frames when the file has no VBR header (Xing or VBRI). With a quiet
# start, a title of 20 s is announced for 102 s. With a busy start, for 13 s:
# it plays on while its remaining time says 0. The scheduler waits for the last
# seconds of a title to push a jingle or a cut, and pushed them in the middle
# of such a title. libmad counts the frames: the exact length, in a few
# milliseconds. A local MP3 only: the decoder knows the length of the other
# formats. playout/tests/antenna.py plays these two titles.
def exact_duration(sound) =
  if string.contains(prefix="/", sound) and r/\.mp3$/i.test(sound) then
    d = request.duration(resolvers=["mad"], resolve_metadata=false, sound) ?? 0.
    if d > 0. and d < 100000. then d else 0. end
  else
    0.
  end
end

# The exact length a request got at its push, 0. without one.
def pushed_duration(r) =
  md = request.metadata(r)
  float_of_string(default=0., md["radiotomate_duration"])
end

# What is left of the title a queue plays: its exact length less what the queue
# has played of it. Else the decoder's estimate. `current()` is the title that
# plays, the next one only once it has started; no test on `request.status`,
# which stays "ready" for a title on air in Liquidsoap 2.4.
def queue_remaining(q, estimate) =
  playing = q.current()
  exact = if null.defined(playing) then pushed_duration(null.get(playing)) else 0. end
  if exact > 0. then max(0., exact - max(0., q.elapsed())) else finite_seconds(estimate) end
end

def track_remaining() =
  sid = on_air_queue()
  if sid == "jingles" then
    queue_remaining(jingles_queue, jingles.remaining())
  elsif sid == "jingles_wait" then
    queue_remaining(jingles_wait_queue, jingles_wait.remaining())
  elsif sid == "carts" then
    queue_remaining(carts_queue, carts.remaining())
  elsif sid == "carts_wait" then
    queue_remaining(carts_wait_queue, carts_wait.remaining())
  elsif sid == "stream" then
    finite_seconds(stream.remaining())
  elsif sid == "relay" then
    finite_seconds(relay.remaining())
  else
    r = queue_remaining(autodj_queue, autodj.remaining())
    if r > 0. then r else finite_seconds(programs.remaining()) end
  end
end

def effective_gain() =
  if current_source_id() == "stream" then
    1.0
  else
    voiceover_gain()
  end
end

def ramp_gain(target, dur) =
  voiceover_ramp := voiceover_ramp() + 1
  gen = voiceover_ramp()
  start = voiceover_gain()
  t0 = time()
  dur = max(0.05, dur)
  def rec vo_tick() =
    if gen != voiceover_ramp() then
      ()
    else
      t = time() - t0
      if t >= dur then
        voiceover_gain := target
      else
        p = 0.5 - 0.5 * cos(3.14159265 * t / dur)
        voiceover_gain := start + (target - start) * p
        thread.run(delay=0.05, fast=true, vo_tick)
      end
    end
  end
  vo_tick()
end

voiceover_pcm = input.ffmpeg(
  id="voiceover_pcm",
  max_buffer=0.25,
  format="s16le",
  string_args=[("sample_rate", "48000"), ("channels", "1")],
  "tcp://0.0.0.0:6802?listen=1"
)

voiceover_mic = fallback(track_sensitive=false, [
  stereo(voiceover_pcm),
  blank(id="voiceover_silent")
])

ducked_bed = amplify(id="voiceover_duck", {effective_gain()}, bed)
radio = add(id="voiceover_mix", normalize=false, [ducked_bed, voiceover_mic])
radio = rms(id="onair_meter", duration=0.2, radio)

silence_s = ref(0.)
rms_db = ref(-90.)
rss_mb = ref(0.)
cpu_pct = ref(0.)
cpu_prev_ticks = ref(-1.)
cpu_prev_t = ref(0.)

BLANK_AMP = 5.62341325e-3

def meter_tick() =
  v = radio.rms()
  silent =
    if v < 0. then
      rms_db := v
      v < BLANK_THRESHOLD
    elsif v < BLANK_AMP then
      rms_db := BLANK_THRESHOLD
      true
    else
      rms_db := 0.
      false
    end
  if silent then
    silence_s := silence_s() + 0.25
  else
    silence_s := 0.
  end
end

thread.run(every=0.25, delay=2., fast=true, meter_tick)

def sh_line(cmd) =
  list.hd(string.split(separator="\n", process.run(cmd).stdout))
end

def proc_rss_mb() =
  try
    kb = int_of_string(sh_line("awk '/^VmRSS:/ {print $2}' /proc/1/status"))
    float_of_int(kb) / 1024.
  catch err do
    ignore(err)
    rss_mb()
  end
end

def proc_cpu_ticks() =
  try
    float_of_string(sh_line("sed 's/.*)//' /proc/1/stat | awk '{print $12+$13}'"))
  catch err do
    ignore(err)
    -1.
  end
end

def machine_tick() =
  rss_mb := proc_rss_mb()
  ticks = proc_cpu_ticks()
  now = time()
  prev_t = cpu_prev_t()
  prev = cpu_prev_ticks()
  if ticks >= 0. and prev >= 0. and prev_t > 0. then
    dt = now - prev_t
    if dt > 0.2 then
      cpu_pct := max(0., min(100., 100. * (ticks - prev) / 100. / dt))
    end
  end
  if ticks >= 0. then
    cpu_prev_ticks := ticks
    cpu_prev_t := now
  end
end

thread.run(every=1., delay=2., fast=false, machine_tick)

def voiceover_watch() =
  rem = track_remaining()
  voiceover_remaining := rem
  if voiceover_on() and current_source_id() != "stream" and rem > 0. and rem <= VOICEOVER_RESTORE_S then
    voiceover_on := false
    ramp_gain(1.0, voiceover_fade())
  end
end

thread.run(every=0.5, delay=1., fast=true, voiceover_watch)



############################ ♫ OUTPUT ♫ ########################################

def get_encoder(family, quality) = 
  quality_i = int_of_float(quality)
  if family == 'mp3cbr' then
    %mp3.cbr(bitrate=quality_i, samplerate=44100, stereo=true)
  elsif family == 'mp3vbr' then
    %mp3.vbr(quality=quality_i)
  elsif family == 'flac' then
    %ogg(
      %flac(samplerate=44100, channels=2, compression=quality_i, bits_per_sample=16)
    )
  elsif family == 'vorbiscbr' then
    %vorbis.cbr(samplerate=44100, channels=2, bitrate=quality_i)
  elsif family == 'vorbisvbr' then
    %vorbis(samplerate=44100, channels=2, quality=quality)
  elsif family == 'wav' then
    %wav()
  else
    intro = "skipping output configuration block, unsupported value for 'encoder': "
    outro = " (should be one of: mp3cbr, mp3vbr, flac, vorbiscbr, vorbisvbr, wav)"
    log.important(intro ^ family ^ outro)
    null
  end
end

def output_build_pulse(config) =
  output.pulseaudio(radio, device=config.device)
end

def output_build_alsa(config) =
  output.alsa(radio, device=null.get(config.device, default="default"))
end

# Icecast outputs state for `/health`: every declared mount is listed in
# icecast_targets; icecast_connected only holds the ones currently streaming.
icecast_targets = ref([])
icecast_connected = ref([])

def icecast_mark(target, up) =
  without = list.filter(fun (t) -> t != target, icecast_connected())
  icecast_connected := if up then [target, ...without] else without end
  state = if up then "connected" else "disconnected" end
  log.important("icecast #{target} #{state}")
end

def output_build_icecast(config) =
  if not null.defined(config.encoder) or
    not null.defined(config.quality) or
    not null.defined(config.host) or
    not null.defined(config.port) or
    not null.defined(config.mount)
    then
    log.important("skipping icecast configuration block: it needs to contain at least encoder, quality, host, port and mount")
    null
  else
    enc = get_encoder(null.get(config.encoder, default=""), null.get(config.quality, default=1.))
    if null.defined(enc) then
      hostname = null.get(config.host)
      port = int_of_float(null.get(config.port))
      mount = null.get(config.mount)
      password = null.get(config.password, default="")
      target = "#{hostname}:#{port}/#{mount}"
      icecast_targets := [target, ...icecast_targets()]
      output.icecast(
        host=hostname,
        port=port,
        mount=mount,
        password=password,
        on_connect={icecast_mark(target, true)},
        on_disconnect={icecast_mark(target, false)},
        null.get(enc),
        radio
      )
    else
      null
    end
  end
end

def outputs_builder(config) =
  # FIXME these two lines are a workaround while waiting for https://github.com/savonet/liquidsoap/issues/4285
  opt = {str="", flo=1.}
  config = true ? config : {driver="", device=opt?.str, encoder=opt?.str, quality=opt?.flo, host=opt?.str, port=opt?.flo, mount=opt?.str, password=opt?.str}

  if config.driver == "pulseaudio" then
    output_build_pulse(config)
  elsif config.driver == "alsa" then
    output_build_alsa(config)
  elsif config.driver == "icecast" then
    output_build_icecast(config)
  else
    intro = "skipping output configuration block, unsupported value for 'driver': "
    outro = " (should be 'alsa', 'pulseaudio' or 'icecast')"
    log.important(intro ^ config.driver ^ outro)
    null
  end
end

outputs = null.get(conf.playout_process_config.outputs, default=[])
if list.length(outputs) == 0 then
  crash("\n\n\n\n\n !!!! No output has been set-up !!!!\n\n\n\n\n" ^
    "Edit the file #{path_to_config} to define outputs (remove all # before the example block that fits your needs)\n\n\n")
end

outputs = list.filter_map(outputs_builder, outputs)
outputs_nb = string.of_int(list.length(outputs))
log.important("started #{outputs_nb} outputs")

#################### PLAYOUT LOG TO SCHEDULER SERVICE ##########################

# raw metadata can weight a few megabytes so we'll filter_md only once
current_md = ref(json())
on_air_title = ref("")
on_air_artist = ref("")

# keep a pre-computed version of queued requests' metadata
next_jingle = ref({title="", artist="", rid=-1, initial_uri="", duration=0.})
next_autodj = ref({title="", artist="", rid=-1, initial_uri="", duration=0.})
next_cart = ref({title="", artist="", rid=-1, initial_uri="", duration=0.})

def filter_md(md)
  let data = json()
  list.iter(fun (v) -> if MD_FIELDS[fst(v)] == 'keep' then data.add(fst(v),snd(v)) end, md)
  data
end

#### Metadata log

def post_to_log(md)
  data = filter_md(md)
  data.add("on_air", time.string('%Y-%m-%d %H:%M:%S'))
  current_md := data
  on_air_title := md["title"]
  on_air_artist := md["artist"]
  # As-run truth: a request pushed by the scheduler carries the queue it came
  # from (annotate radiotomate_queue). Transitions in LS 2.3 are unreliable
  # (#4179), so `current_source_id` alone mislabelled carts music as autodj.
  pushed_queue = md["radiotomate_queue"]
  src = if pushed_queue != "" then pushed_queue else on_air_source() end
  data.add("source", src)
  _ = post_to_radiotomate("/metadata_log", data)
end

radio.on_metadata(synchronous=false, post_to_log)

#### Regular update of the "live" panel

cached_duration_uri = ref("")
cached_duration = ref(0.)

def cue_duration_uri(uri) =
  if uri == "" then
    0.
  elsif uri == cached_duration_uri() then
    cached_duration()
  else
    d = request.duration(uri) ?? 0.
    d = if d > 0. and d < 100000. then d else 0. end
    cached_duration_uri := uri
    cached_duration := d
    d
  end
end

def cue_duration(r) =
  exact = pushed_duration(r)
  if exact > 0. then exact else cue_duration_uri(request.uri(r)) end
end

def fill_next(data, field, q, cached)
  cached = true ? cached : ref({title="", artist="", rid=-1, initial_uri="", duration=0.}) # FIXME this is a workaround while waiting for https://github.com/savonet/liquidsoap/issues/4285
  try
    current_maybe = q.current()
    playing_id = if null.defined(current_maybe) then request.id(null.get(current_maybe)) else -1 end
    current_status = if null.defined(current_maybe) then request.status(null.get(current_maybe)) else "" end
    # current() est le vrai suivant seulement si la file n'est pas à l'antenne (ready).
    # Sinon c'est le titre en cours : on lit la file, jamais un RID playing.
    r = if current_status == "ready" then
      begin
        cur = null.get(current_maybe)
        md = request.metadata(cur)
        # Prêt mais déjà à l'antenne (même fichier poussé dans deux files) : chercher derrière.
        if md["title"] == on_air_title() and md["artist"] == on_air_artist() then
          list.find(fun (cand) -> request.status(cand) == "ready" and request.id(cand) != request.id(cur), q.queue())
        else
          cur
        end
      end
    else
      list.find(fun (cand) -> request.status(cand) == "ready" and request.id(cand) != playing_id, q.queue())
    end
    rid = request.id(r)

    if rid == cached().rid then
      log.debug("#{field} return cached RID#{rid}, #{q.length()} items enqueued")
      data.add(field, cached())
    else
      md = request.metadata(r)
      cached := {title=md["title"], artist=md["artist"], rid=rid, initial_uri=request.uri(r), duration=cue_duration(r)}
      log.debug("#{field} update cache with RID#{rid}, #{q.length()} items enqueued")
      data.add(field, cached())
    end

  catch err : [error.not_found] do
    cached := {title="", artist="", rid=-1, initial_uri="", duration=0.}
    log.debug("#{field} is empty")
    data.add(field, {rid=-1})
    ignore(err)
  end
end

# The next sound of a queue, or of the one where its sounds wait for the end of
# a title. What `q` holds goes first: it cuts in, or follows what cut in.
def fill_next_two(data, field, q, q_wait, cached)
  cached = true ? cached : ref({title="", artist="", rid=-1, initial_uri="", duration=0.}) # FIXME the workaround of fill_next
  fill_next(data, field, q, cached)
  if cached().rid == -1 then
    fill_next(data, field, q_wait, cached)
  end
end

def post_to_live()
  data = current_md()
  data.add("source", on_air_source())
  rem = track_remaining()
  voiceover_remaining := rem
  data.add("remaining", string.float(rem))
  data.add("elapsed", string.float(finite_seconds(bed.elapsed())))
  data.add("time", time.string('%Y-%m-%dT%H:%M:%S%z'))

  # A sound that waits counts in its queue: the scheduler pushed it there.
  fill_next_two(data, "next_jingle", jingles_queue, jingles_wait_queue, next_jingle)
  fill_next(data, "next_autodj", autodj_queue, next_autodj)
  fill_next_two(data, "next_cart", carts_queue, carts_wait_queue, next_cart)
  data.add("jingles_queued", jingles_queue.length() + jingles_wait_queue.length())
  data.add("autodj_queued", autodj_queue.length())
  data.add("carts_queued", carts_queue.length() + carts_wait_queue.length())

  _ = post_to_radiotomate("/live", data)
end

thread.run(every=1., delay=1., fast=false, post_to_live)

######################## SCHEDULER'S ENDPOINTS ##############################

#### Version

def version_GET(_, res) =
  res.json({version=liquidsoap.version})
end

harbor.http.register(port=API_PORT, method="GET", "/version", version_GET)

def health_GET(_, res) =
  let data = json()
  src = on_air_source()
  data.add("status", "live")
  data.add("silence_s", string.float(silence_s()))
  data.add("rms_db", string.float(rms_db()))
  data.add("rms", string.float(radio.rms()))
  data.add("gain", string.float(effective_gain()))
  data.add("on", if voiceover_on() then "true" else "false" end)
  data.add("harbor_min", string.float(conf.playout_process_config.input_min_buffer))
  data.add("harbor_max", string.float(conf.playout_process_config.input_max_buffer))
  data.add("source", src)
  data.add("rss_mb", string.float(rss_mb()))
  data.add("cpu_pct", string.float(cpu_pct()))
  connected = icecast_connected()
  down = list.filter(fun (t) -> not list.mem(t, connected), icecast_targets())
  data.add("icecast_targets", string.concat(separator=",", icecast_targets()))
  data.add("icecast_connected", string.concat(separator=",", connected))
  data.add("icecast_down", string.concat(separator=",", down))
  if src == "stream" then
    buf = finite_seconds(stream.remaining())
    if buf > 0. then
      data.add("harbor_s", string.float(buf))
    end
  end
  res.json(data)
end

harbor.http.register(port=API_PORT, method="GET", "/health", health_GET)

def voiceover_status() =
  let data = json()
  data.add("on", if voiceover_on() then "true" else "false" end)
  data.add("fade", string.float(voiceover_fade()))
  data.add("remaining", string.float(voiceover_remaining()))
  data.add("gain", string.float(effective_gain()))
  data.add("mic", "false")
  data
end

def voiceover_GET(_, res) =
  res.json(voiceover_status())
end

harbor.http.register(port=API_PORT, method="GET", "/voiceover", voiceover_GET)

def voiceover_POST(req, res) =
  let json.parse (posted:{on: bool, fade: float?}) = req.body()
  fade_s = clamp_fade(posted.fade ?? voiceover_fade())
  remaining = voiceover_remaining()
  if current_source_id() == "stream" then
    let err = json()
    err.add("error", "harbor")
    err.add("remaining", string.float(remaining))
    res.status_code(409)
    res.json(err)
  elsif posted.on and remaining > 0. and remaining <= VOICEOVER_RESTORE_S + fade_s then
    let err = json()
    err.add("error", "trop proche")
    err.add("remaining", string.float(remaining))
    res.status_code(409)
    res.json(err)
  else
    voiceover_fade := fade_s
    voiceover_on := posted.on
    target = if posted.on then VOICEOVER_DUCK else 1.0 end
    ramp_gain(target, fade_s)
    res.json(voiceover_status())
  end
end

harbor.http.register(port=API_PORT, method="POST", "/voiceover", voiceover_POST)

#### Skip / max duration / stop relay

def live_DELETE(req, res) =
  radiotomate_sound_id = req.query["radiotomate_sound_id"]
  queue_name = req.query["queue"]
  if string.length(req.query["relay"]) > 0 then
    relay.stop()
    res.status_code(200)
  elsif string.length(radiotomate_sound_id) > 0 then
    # this implements carts' max duration - when we don't need to skip, return 204 No Content
    res.status_code(204)
    # A sound that waited for the end of a title plays from its own queue.
    waited = on_air_queue() == "carts_wait"
    playing_maybe = if waited then carts_wait_queue.current() else carts_queue.current() end
    if null.defined(playing_maybe) then
      playing = null.get(playing_maybe)
      md = request.metadata(playing)
      left = if waited then carts_wait_queue.remaining() else carts_queue.remaining() end
      if md["radiotomate_sound_id"] == radiotomate_sound_id and
        left > 1.
        then
          rid = request.id(playing)
          log("Forcing max duration for sound_id##{radiotomate_sound_id} (was RID#{rid})")
          if waited then carts_wait_queue.skip() else carts_queue.skip() end
          res.status_code(200)
      end
    end
  elsif string.length(queue_name) > 0 then
    # Hard-sync: drop the cut Auto-DJ track without skipping the output bed
    # (bed.skip would start the next Auto-DJ request before the cart is ready).
    if queue_name == "autodj" then
      # Only a title that has played: the one a sound has cut. Behind a sound
      # that waited for the end of a title, the queue holds the next one, of
      # which it has played one frame: a skip would drop it whole.
      if null.defined(autodj_queue.current()) and autodj_queue.elapsed() >= AUTODJ_PLAYED_S then
        autodj_queue.skip()
        log("Skipping autodj queue")
      end
      res.status_code(200)
    elsif queue_name == "jingles" then
      if on_air_queue() == "jingles_wait" then jingles_wait_queue.skip() else jingles_queue.skip() end
      res.status_code(200)
    elsif queue_name == "carts" then
      if on_air_queue() == "carts_wait" then carts_wait_queue.skip() else carts_queue.skip() end
      res.status_code(200)
    else
      res.status_code(400)
    end
  else
    bed.skip()
    res.status_code(200)
  end
end

harbor.http.register(port=API_PORT, method="DELETE", "/live", live_DELETE)

#### push content

# Where a sound pushed to the jingles or to the carts goes, once resolved.
# - Told to wait, it goes at the end of the title on air; a sound of a cart,
#   at the end of the jingle on air too. Behind a sound of a cart or a live, a
#   jingle follows them as it always did: from the queue that cuts, which
#   waits behind them.
# - While a sound that waited is on air, one of its kind follows it, told to
#   wait or not: it does not cut it.
# - While a sound waits for the end of the title on air, a jingle waits with it,
#   told to or not, as a pad: cutting in, it would leave the end of the title
#   to come back after it, and start at once a sound of a cart that waits.
# - Else it cuts what plays: a gesture, a cut on the minute.
def push_where_it_goes(queue_name, wait, r) =
  on_air = on_air_queue()
  a_sound_waits = jingles_wait_queue.length() > 0 or carts_wait_queue.length() > 0
  if queue_name == "jingles" then
    if on_air == "jingles_wait" or
      (wait and (on_air == "autodj" or on_air == "jingles")) or
      (on_air == "autodj" and a_sound_waits)
    then
      jingles_wait_queue.push(r)
    else
      jingles_queue.push(r)
    end
  elsif queue_name == "carts" then
    if on_air == "carts_wait" or
      (wait and (on_air == "autodj" or on_air == "jingles" or on_air == "jingles_wait"))
    then
      carts_wait_queue.push(r)
    else
      carts_queue.push(r)
    end
  else
    autodj_queue.push(r)
  end
end

def queue_POST(req, res) =
  queue_name = req.query["queue"]
  let json.parse (posted:{
    path: string,
    artist: string?,
    title: string?,
    radiotomate_sound_id: int?,
    radiotomate_item_id: string?,
    rg_track_gain: float?,
    wait: bool?,
  }) = req.body()

  pushed = time()
  exact = exact_duration(posted.path)
  annotated = "annotate:pushed=\"#{pushed}\",radiotomate_queue=\"#{queue_name}\"" ^
    if null.defined(posted.radiotomate_sound_id) then
      ",radiotomate_sound_id=\"#{null.get(posted.radiotomate_sound_id)}\""
    else
      ""
    end
    ^
    # Rundown item id: lets the scheduler link the as-run row to the exact
    # planned item (titles and sound ids repeat in a small rotation).
    if null.defined(posted.radiotomate_item_id) then
      ",radiotomate_item_id=\"#{null.get(posted.radiotomate_item_id)}\""
    else
      ""
    end
    ^
    if null.defined(posted.title) then
      ",title=\"#{null.get(posted.title)}\""
    else
      ""
    end
    ^
    if null.defined(posted.artist) then
      ",artist=\"#{null.get(posted.artist)}\""
    else
      ""
    end
    ^
    if null.defined(posted.rg_track_gain) then
      ",rg_track_gain=\"#{null.get(posted.rg_track_gain)}\""
    else
      ""
    end
    ^
    # Read by track_remaining and by the cues of the queues: see exact_duration.
    if exact > 0. then ",radiotomate_duration=\"#{exact}\"" else "" end
    ^ ":" ^ posted.path

  try
    q =
      if queue_name == "autodj" then
        autodj_queue
      elsif queue_name == "jingles" then
        jingles_queue
      elsif queue_name == "carts" then
        carts_queue
      else
        error.raise(error.not_found, "unknown queue #{queue_name}")
      end

    r = request.create(annotated)
    if (request.resolve(r, content_type=q)) then
      # Once resolved: what is on air may have changed meanwhile.
      push_where_it_goes(queue_name, posted.wait ?? false, r)
      res.status_code(200)
      res.json({ok=request.id(r)})
    else
      res.status_code(400)
      message = request.log(r)
      res.json({error="cannot resolve #{path} - #{message}"})
    end
  catch err : [error.not_found] do
    res.status_code(400)
    res.json({error=err.message})
  end
end

harbor.http.register(port=API_PORT, method="POST", "/queue/:queue", queue_POST)


# `spare_next`: the next title of the queue stays, however long it has waited.
# The scheduler keeps one title ready in the Auto-DJ queue behind what plays,
# a recorded show of an hour as well: taken out after ten minutes, it left the
# queue empty at the end of the show, and its line in the conducteur for good.
def _queue_clean_result(q, max_age, ~spare_next=false)
  now = time()
  removed = ref(0)
  kept = ref(0)
  playing = ref(-1)
  spared = ref(not spare_next)
  current_maybe = q.current()
  if null.defined(current_maybe) then
    playing := request.id(null.get(current_maybe))
  end
  list.iter(fun (r) -> begin
    rid = request.id(r)
    if rid == playing() then
      kept := kept() + 1
    elsif not spared() then
      spared := true
      kept := kept() + 1
    else
      md = request.metadata(r)
      pushed_s = md["pushed"]
      if string.length(pushed_s) == 0 then
        kept := kept() + 1
      else
        try
          age = now - float_of_string(pushed_s)
          if age > max_age then
            q.remove_request_id(rid)
            removed := removed() + 1
          else
            kept := kept() + 1
          end
        catch err do
          kept := kept() + 1
          ignore(err)
        end
      end
    end
  end, q.queue())
  {removed=removed(), kept=kept()}
end


def queue_clean_POST(req, res) =
  max_age = ref(600.)
  try
    let json.parse (posted:{max_age_seconds: float?}) = req.body()
    if null.defined(posted.max_age_seconds) then
      max_age := null.get(posted.max_age_seconds)
    end
  catch err do
    ignore(err)
  end
  age = max_age()
  clamped =
    if age < 30. then
      30.
    elsif age > 7200. then
      7200.
    else
      age
    end
  # A queue, and the one where its sounds wait for the end of a title.
  def both(q, q_wait)
    cut = _queue_clean_result(q, clamped)
    waiting = _queue_clean_result(q_wait, clamped)
    {removed=cut.removed + waiting.removed, kept=cut.kept + waiting.kept}
  end
  res.status_code(200)
  res.json({
    autodj=_queue_clean_result(autodj_queue, clamped, spare_next=true),
    jingles=both(jingles_queue, jingles_wait_queue),
    carts=both(carts_queue, carts_wait_queue)
  })
end

harbor.http.register(port=API_PORT, method="POST", "/queue/clean", queue_clean_POST)


# `item_ids`: the rundown items of the removed requests, which the scheduler
# closes. The request a queue has loaded (`current`, on air or next) stays.
def _queue_flush_result(q)
  removed = ref(0)
  kept = ref(0)
  item_ids = ref([])
  playing = ref(-1)
  current_maybe = q.current()
  if null.defined(current_maybe) then
    playing := request.id(null.get(current_maybe))
  end
  list.iter(fun (r) -> begin
    rid = request.id(r)
    if rid == playing() then
      kept := kept() + 1
    else
      md = request.metadata(r)
      item_id = md["radiotomate_item_id"]
      if item_id != "" then
        item_ids := [...item_ids(), item_id]
      end
      q.remove_request_id(rid)
      removed := removed() + 1
    end
  end, q.queue())
  {removed=removed(), kept=kept(), item_ids=item_ids()}
end


ALL_QUEUES = ["autodj", "jingles", "carts"]

# Body is optional: `{}` / empty → flush everything; `{"queues": ["jingles",
# "autodj"]}` → only those (harbor return keeps the carts stock).
def _flush_wanted(body)
  if string.trim(body) == "" then
    ALL_QUEUES
  else
    try
      let json.parse (posted : {queues: [string]?}) = body
      posted.queues ?? ALL_QUEUES
    catch _ do
      log(label="queue_flush", level=3, "unreadable body, flushing all queues")
      ALL_QUEUES
    end
  end
end

def queue_flush_POST(req, res) =
  wanted = _flush_wanted(req.body())
  def maybe(name, q)
    if list.mem(name, wanted) then
      _queue_flush_result(q)
    else
      {removed=0, kept=q.length(), item_ids=[]}
    end
  end
  # A queue, and the one where its sounds wait for the end of a title: a sound
  # that still waits is not loaded, and leaves with the others.
  def both(name, q, q_wait)
    cut = maybe(name, q)
    waiting = maybe(name, q_wait)
    {
      removed=cut.removed + waiting.removed,
      kept=cut.kept + waiting.kept,
      item_ids=[...cut.item_ids, ...waiting.item_ids]
    }
  end
  res.status_code(200)
  res.json({
    autodj=maybe("autodj", autodj_queue),
    jingles=both("jingles", jingles_queue, jingles_wait_queue),
    carts=both("carts", carts_queue, carts_wait_queue)
  })
end

harbor.http.register(port=API_PORT, method="POST", "/queue/flush", queue_flush_POST)


def relay_POST(req, res) =
  query_url = req.query["url"]
  if string.length(query_url) > 0 then
    relay.set_url(query_url)
    relay.start()
    res.status_code(200)
    res.json({ok=relay.status()})
  else
    res.status_code(400)
    res.json({error="'url' query parameter is empty"})
  end
end

harbor.http.register(port=API_PORT, method="POST", "/relay", relay_POST)

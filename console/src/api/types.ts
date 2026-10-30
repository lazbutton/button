export type PositionKind = "musique" | "jingle" | "son" | "pub";

export type ClockPosition = {
  id?: number;
  kind: PositionKind;
  when: "sequential" | "anchored";
  cart: string | null;
  cart_id?: number | null;
  category: string | null;
  fallback_cart: string | null;
  fallback_cart_id?: number | null;
  minute?: number | null;
  sync?: "dure" | "molle" | null;
};

export type Clock = {
  id: number;
  version?: number;
  name: string;
  fallback_cart: string;
  fallback_cart_id?: number | null;
  motif: ClockPosition[];
  anchors: ClockPosition[];
};

export type Slot = {
  id: number;
  version?: number;
  day_of_week: number;
  minute: number;
  title: string;
  color: string;
  clock_id: number | null;
  clock: string | null;
};

export type Category = {
  id: number;
  name: string;
  query: string;
  empty_query: string;
  count: number;
};

export type Sound = {
  id: number;
  rank: number;
  title: string;
  duration: number;
  active: boolean;
  available: boolean;
  gain: number | null;
  peak: number | null;
  last_played: string | null;
  uploader: string | null;
  path?: string;
};

export type CartMode = "playlist" | "playlist_loop" | "random" | "relay";
export type ScheduleMode = "clock" | "timed" | "jingles";
export type CartQueue = "carts" | "autodj";

export type Cart = {
  id: number;
  version?: number;
  title: string;
  notes: string;
  mode: CartMode;
  url: string | null;
  queue: CartQueue | null;
  max_duration: number | null;
  average_duration: number;
  schedule_mode: ScheduleMode;
  schedule_correct: boolean;
  schedule_summary: string;
  schedule_advanced: boolean;
  schedule_year: string;
  schedule_month: string;
  schedule_day: string;
  schedule_week: string;
  schedule_day_of_week: string;
  schedule_hour: string;
  schedule_minute: string;
  schedule_second: string;
  next_sound_id: number | null;
  bank_folder?: string | null;
  ident_pads?: boolean;
  finder_path?: string | null;
  sounds: Sound[];
  delta?: boolean;
};

export type BankFolder = {
  path: string;
  count: number;
};

export type BankResponse = {
  available: boolean;
  folders: BankFolder[];
};

export type UserPermissions = {
  admin?: boolean;
  stream?: boolean;
  live?: boolean;
  carts?: boolean;
  not_audio?: boolean;
  autodj?: boolean;
};

export type User = {
  id: number;
  username: string;
  notes: string;
  permissions: UserPermissions;
};

export type UsersResponse = { users: User[] };

/** Le jeton d'encodeur d'un compte : sa date de création, jamais le jeton lui-même. */
export type StreamTokenState = { created_at: string | null };

/** Un jeton neuf : la seule fois où le moteur le donne. */
export type NewStreamToken = { token: string; created_at: string };

export type RundownItem = {
  id?: string;
  at: string;
  kind: string;
  when: string;
  resource: string;
  queue: string;
  status: string;
  status_code?: string;
  reason?: string | null;
  clock: string;
  daypart: string;
  minute?: number;
  sync?: string;
  category?: string;
  cart?: string;
  cart_id?: number | null;
  sound_id?: number | null;
  beets_id?: number | null;
  duration?: number;
  programming_version?: string;
  fallback_used?: boolean;
  origin?: string;
  path?: string;
  artist?: string;
  title?: string;
  clock_id?: number | null;
  position_id?: number | null;
};

export type RundownSummary = {
  next_anchor: {
    at?: string;
    minute?: number;
    kind?: string;
    resource?: string;
    sync?: string;
  } | null;
  counts: {
    items: number;
    musique: number;
    jingle: number;
    son: number;
    pub: number;
    secours: number;
    sauté: number;
  };
};

export type Rundown = {
  now: string;
  horizon_min: number;
  clock: string | null;
  daypart: string | null;
  programming_version?: string;
  summary?: RundownSummary;
  items: RundownItem[];
  action?: "refresh" | "reset";
};

export type ClocksResponse = { clocks: Clock[] };
export type SlotsResponse = { slots: Slot[] };
export type CategoriesResponse = { categories: Category[] };
export type CartsResponse = { carts: Cart[] };

export type Cue = {
  title: string;
  artist: string;
  rid: number;
  initial_uri: string;
};

export type LiveStatus = "offline" | "simulating" | "playing";

export type EmissionState = "waiting" | "on_air";

export type Emission = {
  id: number;
  version?: number;
  scope: "weekly" | "session";
  title: string;
  artist: string;
  day_of_week?: number | null;
  start_minute?: number | null;
  end_minute?: number | null;
  host_username?: string;
  starts_at?: string | null;
  ends_at?: string | null;
};

export type LiveEmission = {
  id: number;
  title: string;
  artist: string;
  state: EmissionState;
  until?: string | null;
  /** "weekly", "session", or "dated" for a broadcast of the Agenda. */
  scope?: string;
  /** Agenda only: "set" or "live". */
  kind?: string;
  start_minute?: number | null;
  day_of_week?: number | null;
};

export type EmissionNext = {
  id: number;
  title: string;
  artist: string;
  at: string;
  until?: string;
  day_of_week?: number;
  start_minute?: number;
  end_minute?: number;
};

export type EmissionsResponse = {
  emissions: Emission[];
  current: LiveEmission | null;
  next: EmissionNext | null;
};

export type LiveSnapshot = {
  status: LiveStatus;
  source?: string;
  artist?: string;
  title?: string;
  album?: string;
  kind?: string;
  remaining?: number;
  elapsed?: number;
  duration?: number;
  on_air?: string;
  initial_uri?: string;
  radiotomate_sound_id?: string;
  next_autodj?: Cue | null;
  next_jingle?: Cue | null;
  next_cart?: Cue | null;
  emission?: LiveEmission | null;
};

// ---- État antenne (GET /antenne/state.json) ----------------------------------

export type AntennePlayout = {
  reachable: boolean;
  source?: string;
  silence_s?: number | null;
  rms_db?: number | null;
  harbor_s?: number | null;
  voiceover?: boolean;
  icecast_targets?: string[];
  icecast_connected?: string[];
  icecast_down?: string[];
};

export type AntenneEngine = {
  heartbeat_age_s: number | null;
  heartbeat_ok: boolean;
  playout_connected: boolean;
  db_ok: boolean;
  tick_run_total?: number;
  tick_gated_total?: number;
};

export type AntenneIncident = {
  kind: string;
  detail: string;
  since_s: number;
  notified: boolean;
};

export type AntenneListeners = {
  target: string;
  host: string;
  mount: string;
  reachable: boolean;
  mounted: boolean;
  connected: boolean | null;
  listeners: number | null;
  listener_peak: number | null;
};

export type AntenneAsRun = {
  on_air: string | null;
  source: string;
  artist: string;
  title: string;
  path: string | null;
  rundown_item_id: string | null;
};

export type AntenneLiveSlot = {
  title: string;
  label: string;
  starts_in_s: number;
  active: boolean;
};

export type AntenneState = {
  at: string;
  demo?: boolean;
  playout: AntennePlayout;
  engine: AntenneEngine;
  incidents: AntenneIncident[];
  listeners: AntenneListeners[];
  asrun: AntenneAsRun[];
  next_live_slot: AntenneLiveSlot | null;
};

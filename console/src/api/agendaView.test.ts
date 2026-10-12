import assert from "node:assert/strict";
import test from "node:test";
import {
  addDays,
  dayLongLabel,
  dayShortLabel,
  durationLabel,
  guestLocalHint,
  inviteLink,
  inviteMessage,
  minuteAt,
  mondayOf,
  nthOfMonth,
  parisWall,
  rangeLabel,
  repeatLabel,
  segments,
  statusOf,
  upcomingByDay,
  wallString,
  weekLabel,
  weekdayOf,
} from "./agendaView.ts";
import type { Diffusion, WeeklyOccurrence } from "./agenda.ts";

test("Paris walls follow summer and winter time", () => {
  assert.deepEqual(parisWall("2026-10-24T20:00:00Z"), { day: "2026-10-24", minute: 22 * 60 });
  assert.deepEqual(parisWall("2026-12-24T21:00:00Z"), { day: "2026-12-24", minute: 22 * 60 });
  assert.deepEqual(parisWall("2026-10-24T22:00+02:00"), { day: "2026-10-24", minute: 22 * 60 });
});

test("days, weeks and labels", () => {
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
  assert.equal(weekdayOf("2026-10-12"), 0);
  assert.equal(weekdayOf("2026-10-18"), 6);
  assert.equal(mondayOf("2026-10-15"), "2026-10-12");
  assert.equal(dayShortLabel("2026-10-12"), "Lun 12");
  assert.equal(dayLongLabel("2026-10-24"), "samedi 24 octobre");
  assert.equal(weekLabel("2026-10-12"), "12 – 18 octobre 2026");
  assert.equal(weekLabel("2026-09-28"), "28 sept. – 4 oct. 2026");
  assert.equal(weekLabel("2026-12-28"), "28 déc. 2026 – 3 janv. 2027");
  assert.equal(durationLabel(120), "2 h");
  assert.equal(durationLabel(90), "1 h 30");
  assert.equal(durationLabel(45), "45 min");
});

test("walls sent to the server, midnight included", () => {
  assert.equal(wallString("2026-10-24", 22 * 60), "2026-10-24T22:00");
  assert.equal(wallString("2026-10-24", 1440), "2026-10-25T00:00");
  assert.equal(wallString("2026-10-24", 1440 + 90), "2026-10-25T01:30");
  assert.equal(minuteAt(50, 100), 720);
  assert.equal(minuteAt(51, 100), 735);
  assert.equal(minuteAt(-5, 100), 0);
  assert.equal(minuteAt(500, 100), 1440);
});

test("a night set is cut into one segment per day", () => {
  assert.deepEqual(segments("2026-11-07T23:00+01:00", "2026-11-08T01:00+01:00"), [
    { day: "2026-11-07", start: 23 * 60, end: 1440, first: true, last: false },
    { day: "2026-11-08", start: 0, end: 60, first: false, last: true },
  ]);
  assert.deepEqual(segments("2026-11-07T22:00+01:00", "2026-11-08T00:00+01:00"), [
    { day: "2026-11-07", start: 22 * 60, end: 1440, first: true, last: true },
  ]);
  assert.equal(
    rangeLabel("2026-11-07T22:00+01:00", "2026-11-08T00:00+01:00"),
    "samedi 7 novembre, 22:00 → 00:00",
  );
});

const base: Diffusion = {
  id: 1,
  version: 1,
  kind: "set",
  title: "Carte blanche",
  starts_at: "2026-11-07T22:00+01:00",
  ends_at: "2026-11-08T00:00+01:00",
  duration_min: 120,
  guest: null,
  host_username: "",
  set_title: "",
  tracklist: "",
  rights: false,
  rights_at: null,
  deadline_at: "2026-11-06T22:00+01:00",
  deposit_closes_at: "2026-11-07T21:30+01:00",
  deposit_open: true,
  series_id: null,
  air_status: "upcoming",
  air_reason: "",
  aired_start: null,
  aired_end: null,
  stop_requested: false,
  prep: "attendu",
  prep_reason: "Set attendu",
  file: null,
  overrun_seconds: null,
};

test("one status per block: the antenna, then the preparation", () => {
  assert.deepEqual(statusOf(base), { label: "Set attendu", tone: "wait", detail: "" });
  assert.equal(statusOf({ ...base, kind: "live" }).label, "Sans animateur");
  assert.deepEqual(statusOf({ ...base, prep: "pret", overrun_seconds: 720 }), {
    label: "Prêt",
    tone: "warn",
    detail: "Dépasse de 12 min",
  });
  assert.equal(statusOf({ ...base, prep: "a_revoir", prep_reason: "Droits non cochés" }).detail, "Droits non cochés");
  assert.equal(statusOf({ ...base, air_status: "on_air" }).tone, "live");
  assert.deepEqual(statusOf({ ...base, air_status: "missed", air_reason: "Set attendu" }), {
    label: "Manquée",
    tone: "missed",
    detail: "Set attendu",
  });
});

test("the guest's link and message", () => {
  const link = inviteLink("https://radio.example/", "abc");
  assert.equal(link, "https://radio.example/invitation#abc");
  const message = inviteMessage({
    station: "BUTTON",
    guest: "DJ Lou",
    title: "Carte blanche",
    start: base.starts_at,
    end: base.ends_at,
    deadline: base.deadline_at,
    link,
  });
  assert.match(message, /Salut DJ Lou !/);
  assert.match(message, /samedi 7 novembre à 22:00 \(heure de Paris\), 2 h/);
  assert.match(message, /avant le vendredi 6 novembre, 22:00, ici : https:\/\/radio\.example\/invitation#abc/);
});

test("the list keeps time order and drops covered weekly shows", () => {
  const weekly: WeeklyOccurrence[] = [
    {
      emission_id: 3,
      date: "2026-11-07",
      title: "Hop Pop Hop",
      artist: "",
      host_username: "",
      starts_at: "2026-11-07T20:00+01:00",
      ends_at: "2026-11-07T22:00+01:00",
      cancelled: false,
      replaced_by: null,
    },
    {
      emission_id: 4,
      date: "2026-11-07",
      title: "Couverte",
      artist: "",
      host_username: "",
      starts_at: "2026-11-07T22:00+01:00",
      ends_at: "2026-11-07T23:00+01:00",
      cancelled: false,
      replaced_by: 1,
    },
  ];
  const groups = upcomingByDay([base], weekly, { from: "2026-11-01" });
  assert.equal(groups.length, 1);
  assert.deepEqual(
    groups[0].entries.map((entry) => entry.type),
    ["weekly", "diffusion"],
  );
  const todoOnly = upcomingByDay([base], weekly, { from: "", onlyTodo: new Set([1]) });
  assert.deepEqual(todoOnly[0].entries.map((entry) => entry.type), ["diffusion"]);
});

test("repeats in words", () => {
  assert.equal(nthOfMonth("2026-11-06"), 1);
  assert.equal(nthOfMonth("2026-11-27"), -1);
  assert.equal(repeatLabel("monthly", 1, 4), "Chaque mois, le 1er vendredi");
  assert.equal(repeatLabel("monthly", -1, 4), "Chaque mois, le dernier vendredi");
  assert.equal(repeatLabel("biweekly", 1, 5), "Un samedi sur deux");
});

test("the guest sees their own hour when it differs", () => {
  assert.equal(guestLocalHint(base.starts_at, base.ends_at, "Europe/Paris"), "");
  assert.equal(
    guestLocalHint(base.starts_at, base.ends_at, "America/Montreal"),
    "16:00 → 18:00 chez toi (Montreal)",
  );
});

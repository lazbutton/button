-- A library that Beets 2.5.1 indexed, as the import loop did up to ARC-06: four
-- tracks imported one by one (-s), their grouping, a gain, a flexible field. Made
-- with beet import and beet modify of 2.5.1, then dumped (sqlite3 .dump). Paths
-- start with @MEDIA@, the bank, and mtime is 0: test_beets_import_loop.py puts back
-- the bank of the test and the dates of its files.
PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE items (id INTEGER PRIMARY KEY, path BLOB, album_id INTEGER, title TEXT, artist TEXT, artists TEXT, artists_ids TEXT, artist_sort TEXT, artists_sort TEXT, artist_credit TEXT, artists_credit TEXT, remixer TEXT, album TEXT, albumartist TEXT, albumartists TEXT, albumartist_sort TEXT, albumartists_sort TEXT, albumartist_credit TEXT, albumartists_credit TEXT, genre TEXT, style TEXT, discogs_albumid INTEGER, discogs_artistid INTEGER, discogs_labelid INTEGER, lyricist TEXT, composer TEXT, composer_sort TEXT, work TEXT, mb_workid TEXT, work_disambig TEXT, arranger TEXT, grouping TEXT, year INTEGER, month INTEGER, day INTEGER, track INTEGER, tracktotal INTEGER, disc INTEGER, disctotal INTEGER, lyrics TEXT, comments TEXT, bpm INTEGER, comp INTEGER, mb_trackid TEXT, mb_albumid TEXT, mb_artistid TEXT, mb_artistids TEXT, mb_albumartistid TEXT, mb_albumartistids TEXT, mb_releasetrackid TEXT, trackdisambig TEXT, albumtype TEXT, albumtypes TEXT, label TEXT, barcode TEXT, acoustid_fingerprint TEXT, acoustid_id TEXT, mb_releasegroupid TEXT, release_group_title TEXT, asin TEXT, isrc TEXT, catalognum TEXT, script TEXT, language TEXT, country TEXT, albumstatus TEXT, media TEXT, albumdisambig TEXT, releasegroupdisambig TEXT, disctitle TEXT, encoder TEXT, rg_track_gain REAL, rg_track_peak REAL, rg_album_gain REAL, rg_album_peak REAL, r128_track_gain REAL, r128_album_gain REAL, original_year INTEGER, original_month INTEGER, original_day INTEGER, initial_key TEXT, length REAL, bitrate INTEGER, bitrate_mode TEXT, encoder_info TEXT, encoder_settings TEXT, format TEXT, samplerate INTEGER, bitdepth INTEGER, channels INTEGER, mtime REAL, added REAL);
INSERT INTO items VALUES(1,'@MEDIA@/10-rotation/Ada - Un.mp3',NULL,'Un','Ada','','','','','','','','','','','','','','','Jazz','',0,0,0,'','','','','','','','rotation',0,0,0,0,0,0,0,'','',0,0,'','','','','','','','','','','','','','','','','','','','','','','','','','','','',-3.25,0.5,NULL,NULL,NULL,NULL,0,0,0,NULL,1.584,48000,'','','','MP3',24000,0,1,0.0,1794674633.5962679);
INSERT INTO items VALUES(2,'@MEDIA@/10-rotation/Bea - Deux.mp3',NULL,'Deux','Bea','','','','','','','','','','','','','','','Jazz; Blues','',0,0,0,'','','','','','','','rotation',0,0,0,0,0,0,0,'','',0,0,'','','','','','','','','','','','','','','','','','','','','','','','','','','','',-3.25,0.5,NULL,NULL,NULL,NULL,0,0,0,NULL,1.584,48000,'','','','MP3',24000,0,1,0.0,1794674633.596956);
INSERT INTO items VALUES(3,'@MEDIA@/20-archives/jazz/Cy - Live.mp3',NULL,'Live','Cy','','','','','','','','','','','','','','','Archive','',0,0,0,'','','','','','','','jazz',0,0,0,0,0,0,0,'','',0,0,'','','','','','','','','','','','','','','','','','','','','','','','','','','','',-3.25,0.5,NULL,NULL,NULL,NULL,0,0,0,NULL,1.584,48000,'','','','MP3',24000,0,1,0.0,1794674633.7475112);
INSERT INTO items VALUES(4,'@MEDIA@/20-archives/jazz/Dan - Live.mp3',NULL,'Live deux','Dan','','','','','','','','','','','','','','','Rock','',0,0,0,'','','','','','','','jazz',0,0,0,0,0,0,0,'','',0,0,'','','','','','','','','','','','','','','','','','','','','','','','','','','','',-3.25,0.5,NULL,NULL,NULL,NULL,0,0,0,NULL,1.584,48000,'','','','MP3',24000,0,1,0.0,1794674633.7483368);
CREATE TABLE item_attributes (
                    id INTEGER PRIMARY KEY,
                    entity_id INTEGER,
                    key TEXT,
                    value TEXT,
                    UNIQUE(entity_id, key) ON CONFLICT REPLACE);
INSERT INTO item_attributes VALUES(1,1,'famille','jazz');
CREATE TABLE albums (id INTEGER PRIMARY KEY, artpath BLOB, added REAL, albumartist TEXT, albumartist_sort TEXT, albumartist_credit TEXT, albumartists TEXT, albumartists_sort TEXT, albumartists_credit TEXT, album TEXT, genre TEXT, style TEXT, discogs_albumid INTEGER, discogs_artistid INTEGER, discogs_labelid INTEGER, year INTEGER, month INTEGER, day INTEGER, disctotal INTEGER, comp INTEGER, mb_albumid TEXT, mb_albumartistid TEXT, mb_albumartistids TEXT, albumtype TEXT, albumtypes TEXT, label TEXT, barcode TEXT, mb_releasegroupid TEXT, release_group_title TEXT, asin TEXT, catalognum TEXT, script TEXT, language TEXT, country TEXT, albumstatus TEXT, albumdisambig TEXT, releasegroupdisambig TEXT, rg_album_gain REAL, rg_album_peak REAL, r128_album_gain REAL, original_year INTEGER, original_month INTEGER, original_day INTEGER);
CREATE TABLE album_attributes (
                    id INTEGER PRIMARY KEY,
                    entity_id INTEGER,
                    key TEXT,
                    value TEXT,
                    UNIQUE(entity_id, key) ON CONFLICT REPLACE);
CREATE INDEX item_attributes_by_entity
                    ON item_attributes (entity_id);
CREATE INDEX album_attributes_by_entity
                    ON album_attributes (entity_id);
COMMIT;

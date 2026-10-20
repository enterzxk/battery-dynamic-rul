# ISU-ILCC DataV2 two-sample receive and extraction protocol

Status: versioned correction prepared after `review_v1.json` BLOCK; not executed. Requires a passing delta review and a fresh exact GO from the project coordinator.

## Frozen scope

- Read only `RPT_json/Release 1.0/G1C1.json` and `RPT_json/Release 1.0/G20C1.json`; both are frozen `train` IDs.
- Use the verified central-directory metadata and exact ETag `"36331bf80f21d00e19a9a45095f542e8"` for `RPT_json.zip` (929,406,930 bytes; official MD5 matches ETag; whole-archive SHA256 remains unknown).
- Windows controller fetches into memory and streams each response directly over SSH to the remote receiver; raw response bytes are never written to Windows disk and the remote host performs no DNS/network access. Each member is fetched by two exact HTTP ranges: 30-byte local header, then exactly filename+extra+central-directory compressed payload. No descriptor or adjacent bytes. Total: four logical GETs; compressed member body 12,403,932 bytes, plus local-header/name/extra bytes; cap 12,500,000 response-body bytes.
- Check every response is HTTP 206 with matching ETag, exact Content-Range and exact length. Check local-header signature, flags, method and name; bit 3 indicates CRC/sizes are deferred, so verify CRC and size against central directory after decompression. Stop on any mismatch; no retry or alternative member.
- Check HTTP status, ETag, exact Content-Range, Content-Length (when present), and range cap before reading; then read at most exact length+1. The local ZIP header provides flags/method/name-length/extra-length; when bit 3 is set, central-directory compressed/uncompressed sizes and CRC are authoritative. Decode raw DEFLATE under the central-directory per-member size and 128 MiB total cap, enforce CRC32 and hash each uncompressed JSON payload, then parse UTF-8 JSON and at most one additional JSON string encoding. Reject unknown schema rather than guessing.

## Data semantics

- Support the documented native list fields only. Preserve RPT list position as the source RPT index; empty/nonfinite capacities remain missing, and records are never deleted or renumbered. Output per-cell JSON contracts with `cell_id`, `group_id`, `role`, `nominal_capacity_ah`, `baseline_stop`, and `records[source_rpt_index,start,stop,capacityAh,valid]`.
- Capacity becomes visible at that RPT's `stop`; never align it to start or fill it from future neighbors. Retain source timestamp strings as-is. Calendar age is a difference from the first observed stop timestamp; start must not exceed stop and parseable stops must strictly increase. RPT index/7-day cadence never creates native cycle/EFC values. Record only top-level keys and whether a native cycle/EFC key is present; otherwise label it unknown.
- First observed capacity at or below 0.2 Ah is a separately named observed nominal-80 endpoint. It is not latent EOL. Do not label non-crossing records right-censored based on this sample.
- Locked IDs are never fetched, parsed, or decoded.

## Expected output and review gate

- `data/processed/ISU_ILCC_DataV2_v1/rpt_observations.jsonl`
- `reports/isu_ilcc_datav2_20261020_data/two_sample_result.json`
- `isu_datav2_two_rpt_once.py` is the Windows memory HTTP/SSH controller; remote `receive_datav2.py`/`prepare_datav2.py` validates GO, claims one-shot execution, stores exact range responses, decodes bounded members, and creates per-cell outputs only if absent.
- The GO must bind the exact delta-review hash, controller-independent runner/receiver hashes, protocol/cohort/scope/archive metadata hashes, source ID 43756491, 929406930-byte size and ETag, current owner, 4 GETs, 12,500,000-byte network cap, 134,217,728-byte uncompressed cap, exact two member names, zero locked reads/fits, and training disallowed. The receiver also checks active owner, current cwd/takeover, heartbeat age, lock hash, GO age <=10 minutes, and exclusive claim creation before the controller can issue GETs.
- On mismatch or failure, write one create-only failure receipt; never overwrite existing claim, raw compressed range, result, or per-cell output. Do one delta review before GO; no smoke or repeated runs.

## Metadata-only full DataV2 plan

Join frozen cohort JSON SHA256 `4469f7f5b6eb8c26a522fa46c4291ec6d03d98e7ae5c20ce7ae77e835b849ae0` (whose `source_valid_ids_sha256` separately identifies Valid_cells.csv as `099876ba651b523f89aeaa417491f25f69fa48321e1f667cb581ad4e27bbc4c5`) to the 252 central-directory records, selecting only train and development members. The verified plan has 125 train members (459,485,686 compressed bytes; 3,533,008,688 uncompressed bytes) and 63 development members (243,832,874 compressed bytes; 1,866,133,238 uncompressed bytes): 188 members total, 703,318,560 compressed bytes and 5,399,141,926 uncompressed bytes. Locked-member reads/decodes are zero. Full-archive SHA256 remains unknown. These totals are metadata-derived; do not treat them as authorization to fetch the full cohort.

## Versioned engineering repair
Prior GO768629 consumed one successful30-byte ZIP metadata-header response then failed before remote storage because SSH flattened a member name containing a space. No raw member body was read. Preserve prior claim/failure; this new request explicitly authorizes one repeated30-byte metadata header plus the three never-read ranges. Current attempt4GET; cumulative5GET and <=12500000body bytes across attempts; no automatic retries. Same two train IDs, no fits/locked; no scientific cap or role change.

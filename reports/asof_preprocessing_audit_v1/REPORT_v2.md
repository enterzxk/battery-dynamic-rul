# MATR/HUST processed as-of 与实体身份审计补充（v2）

日期：2026-10-16（Asia/Shanghai）
实际模型：gpt-6-luna/high
基准报告：同目录 REPORT.md，SHA-256 49455bca17322470fcc06f65677eb42ed98bfc2f301b5aa6042c9ee2fca433b0
动态训练 gate：关闭；本补充不作科学 GO/STOP。

## as-of 资格与未来标签筛选：按控制流澄清

源码证据：

- `run_main.py:74`（SHA-256 `a90a5e39bd3ed26b7dad20b42f2ffaa0d18b78a9cbb76788dfbc3a36357ea216`）默认 `early_cycle_threshold=100`。
- `data_loader.py:487-505`（SHA-256 `f49f22e379bf9012fd284c2ef82e4fdd350e70db760f995d85661f7ac29e1fe2`）先判断 `eol <= early_cycle_threshold` 并直接返回；仅保留 `eol > early_cycle_threshold` 的 cell，随后令 `i` 从 `seq_len` 遍历至 `early_cycle_threshold`（含100），再检查 `i >= eol`。
- 在默认阈值100下，对先通过检查的任何 cell 都有 `i <= 100 < eol`；所以 `i >= eol` 这一分支在该标准路径不可达。若阈值改为其他值，只要仍执行相同先后检查，结论同样成立。此前 v1 把该分支表述为另一个实际 EOL 截 query 的条件，现予更正：它没有在此路径增加第二层 query censoring。
- 对实际的标注规则，`eol` 来自离线标签文件，可能是尾段外推而不是已观测事件。因而可见的未来结局筛选是 **`eol <= 100` 时整颗电芯连同所有 k<100 查询一并排除**。这不是仅为当前 origin 确认 at-risk，而是按完整结局标签决定 cohort eligibility。
- `read_cell_df` 另在 `data_loader.py:456-477` 按 cycle 构造 DataFrame，并在累计 cycle 超过 early threshold 或 eol 时停止。对 `eol > 100` 的标准 early-life 输入，早期100-cycle 上限先触发；该段不显示 EOL 对前100个输入值的额外裁剪。

**合法 at-risk 规则应按 origin 定义。** 对明确观测到的事件时间 T，origin k 可纳入 at-risk 集的条件是截至 k 已知尚未发生事件（T>k）。对右删失电芯，若事件未观察到，最多纳入截至已观测随访 C 的 origins（k≤C），并在 k 时确有存活/未 crossing 记录。该资格只用到 k 时已获得的事件状态与记录覆盖，不要求知道最终寿命。若改用 `estimated_T > k`（由末20点、末端状态或其他未来窗口算出）决定资格，它仍然依赖未来；不能把 estimated_T 当作观测存活状态。对 MATR 81 个非 crossing 的外推标签和 HUST 77 个 nominal 阈值未 crossing 的标签，这一区分尤其适用。

因此应分开报告：

1. **可确认的 as-of 条件**：周期级输入在完整周期结束后才可得；官方 collate 用 mask 将查询 origin 后的早期张量位置置零；已观察到 k 时状态且截至 k 有记录，可以支持 at-risk 资格。
2. **未来标签依赖**：当前 loader 以离线 `eol <= 100` 排除 cell；若 eol 是未来外推标签，这会选择掉在 k<100 时可能仍处于 risk set 的 cell。当前代码本身未实现按逐 query 的观测 crossing/censoring 状态构造风险集。是否有实际 cell 被此门槛排除，须用已存在的小型标签审计摘要或标签文件清单核对；本补充不读任何 pickle，也不推断排除数量。
3. **不额外计为未来 censoring 的项**：被保留 cell 上的 `i >= eol` guard，在该控制流中不可达；不应重复计作 query-level 未来 EOL 选择。

## 现有小型 release 与 alias 对账

本次只读既有回执、静态报告/摘要及小型 stage manifest；未打开 MATR/HUST pickle、ZIP 成员或动态 query 明细。

| 证据 | 固定标识 | 可确认内容 | 边界 |
|---|---|---|---|
| MATR 官方包回执 | `data/raw/MATR/MATR_v11.receipt.json` SHA-256 `7d2c85306d80a1898b3ff88ddb123a12610333d3b5948def4d57d438c740e352` | 归档只读核验；169 个文件名与 split 清单相符（该对应关系由已有 identity audit 记录） | 不证明未列出的跨来源物理身份 |
| MATR 标签重建摘要 | `reports/matr_label_reconstruction_audit/summary.json` SHA-256 `559884595efbc1fddfb88f1afd22dec9387faf48f12dc708536925bff34fbc89` | 169/169 与 pinned 标签算法重建一致；81 尾段外推、88 crossing | 代码一致不证明实际标签生成器版本 |
| MATR identity audit | `reports/matr_identity_code_audit/audit_20261016.md` SHA-256 `40d186425504cc39d1748645478a8540c1519fd9a60b84bdc717a03d5c8beb5b` | train/val/test = 102/34/33；固定名单文件名互斥；列明五组续测合并 | 这是代码/文件名层级，不是 raw serial 或跨来源追踪 |
| HUST v11 stage manifest | `data/source_audit/stage_v11_hust_v11_labels/stage_manifest.json` SHA-256 `656ed7b923ef82e55cb0cd8860afb2ec66d91366d4c1b5ba9f1c62786e337635` | 77 个 HUST 文件；76 个复用字节相同 v9 成员，1 个 HUST_1-8 的 v11 时间内容变化；同记录 v11 labels | v9/v11 字节对账不提供 physical serial/alias 对照 |
| HUST source audit | `reports/data_same_version_staging/hust_v11_source_content_audit.json` SHA-256 `b5292c7cf6893f94ef79c10de11631ebce7bee2cefb34bb8a716c411ba071810` | HUST_1-8 cycle/容量诊断和 v11 label 2359，名义容量1.1Ah、首个 0.8 nominal crossing 未观察到 | 单电芯字段审计，不是全体 physical identity 映射 |

MATR 预处理代码（`preprocess_MATR.py:124-150`）明确合并的五组是：`b1c0 ← b2c7`、`b1c1 ← b2c8`、`b1c2 ← b2c9`、`b1c3 ← b2c15`、`b1c4 ← b2c16`。已知的这五条是 resolved-within-source aliases；右侧续测 ID 不作为独立输出/split entity。现有 identity audit 报告它们各自 canonical 主 ID 只落入一个 split，且五个右侧 alias 均不在 split 名单。该结论不扩展到其它电芯。

## 未解析实体清单

以下是当前固定 split/release 中的 canonical filename IDs；对它们是否与其它 raw 文件、不同数据源或预训练池代表同一物理电芯，现有小型审计均未给出可验证的 serial 映射，因此统一标为 `identity_unverified_external`。其中 MATR 五条上游续测映射本身已合并解析；canonical cell 的外部身份仍未证。

- **MATR，169 canonical IDs**（精确压缩列举；每个存在编号均为 `MATR_b{batch}c{cell}.pkl`）：
  - b1：c0–c45，排除 c8、c10、c12、c13、c22。
  - b2：c0–c47，排除 c7、c8、c9、c15、c16（这五项是已合并的续测 alias，不是 canonical output）。
  - b3：c0–c45，排除 c2、c23、c32、c37、c42、c43。
  - b4：c0–c44。
  - 以上 41+43+40+45=169 个文件名与既有 v11 receipt/split 盘点一致。文件名角色互斥已由既有代码审计确认；其他物理 alias 未解析。
- **HUST，77 canonical IDs**：`HUST_{r}-{c}.pkl`，其中 r=1…10、c=1…8，排除 `HUST_2-1.pkl`、`HUST_5-8.pkl`、`HUST_6-7.pkl`。所有 77 个均缺原始 physical serial/跨来源 alias 映射。本次不把相同 row/column 命名视为物理身份佐证。已知单 cell 审计状态另记：HUST_1-8 在 v11 相比 v9 的差异字段为 time_in_s；HUST_7-5 存在前两 cycle skip 与 loader 重编号问题。

## 下一最小动作

若要构造合法动态 risk set，只用现有逐 cycle 标签/摘要资产，先按每个 origin k 标注 `observed_alive_at_k`、`observed_event_by_k`、`followup_through_k`、`label_status`；禁止以全寿命估计 `eol > 100` 作为观测存活替代。另从明确来源凭证补充 HUST physical serial 及跨来源 alias 映射；当前无法据 filename-only 列表完成。完成前不训练、不跑性能，gate 继续关闭。
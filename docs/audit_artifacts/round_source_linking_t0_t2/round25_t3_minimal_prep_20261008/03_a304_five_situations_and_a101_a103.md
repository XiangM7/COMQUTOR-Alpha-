# 03 A304 五类情形映射与 A101/A103 歧义记录

数据：`03_a304_five_situations_and_a101_a103.json`（脚本 `tools/build_a304_mapping.py`，只读）。被映射的 prompt 是当前生产 `week2.alpha_classifier.v7`，身份 `ac48723f15cf…`。本轮**没有**修改 prompt、代码、阈值、taxonomy 或任何历史 Gold，也没有裁定任何一条。

## 1. 五类情形 → v7 条款

| 情形（John 原文） | 含义 | v7 中处理它的条款（按句号切分的序号） |
|---|---|---|
| S1 提到了估值 | 用了估值词汇，但没有估值结论 | 9（必须说出机制，不能只共享语境）、14（只出现 PEG、valuation、multiple 等词不够） |
| S2 讨论估值风险 | 提出或讨论估值风险（包括以问题形式），但没有断言 | 0、1（先找作者自己当下断言的命题；问题和未认同的引述都不算结论）、12（A304 需要断言估值相对基本面偏贵）、14 |
| S3 反驳估值风险 | 反驳某个估值风险观点（有或没有自己的结论） | 4（实质性的反对仍然选中该 Alpha）、11（反驳或怀疑性表述按其当下断言判断）、14（反驳别人的估值论点、自己没给估值结论，不算） |
| S4 提出条件性风险 | 假设、条件性下行，或"利率上升则估值压缩"这类一般机制 | 0、11（条件性表述按其当下断言判断）、12 |
| S5 已有数据支持估值压缩 | 给出倍数并用自己的话评价为偏贵，或带数据断言估值压缩 | 10（数字已被自己的措辞定性即可）、12 |
| 相邻：价格相对自身历史 | 例如"高于长期均线 71%" | 13（价格技术面观察不构成 A304） |
| 相邻：宏观驱动加估值后果 | 同一句话里既有利率等驱动因素，又有估值后果 | **没有条款规定优先级**（见 Q4） |
| 相邻：泛化风险措辞 | 没有点出任何机制 | 8、9 |

## 2. 条目（A304 18 条，A101/A103 8 条）

"情形"一列是编码代理按文本做的**工程分诊，不是参考标签，永不计分**。这里所有的保存答案都只用于说明，不作为 Gold。

**A304（12 条历史 A304 错误 + 6 条旧池中的其他 A304 边界样本）**

| Gold 集 id | T3 旧样本 | 分诊情形 | 历史 Gold | Candidate-3 | v6 | v7 开发 | ChatGPT | 10-05 标签 | v7 条款 |
|---|---|---|---|---|---|---|---|---|---|
| nh-final-001 | gold-final-001 | 价格相对自身历史 | NONE | A304 | A304 | NONE | NONE | NONE | 13 |
| nh-final-008 | gold-final-008 | 泛化风险 | NONE | A304 | — | — | NONE | NONE | 8、9 |
| nh-final-020 | gold-final-019 | S3 | NONE | A304 | A304 | NONE | NONE | NONE | 4、11、14 |
| nh-final-033 | gold-final-030 | S2 | NONE | A304 | — | 选中后被门槛否决 | NONE | UNABLE_TO_JUDGE | 0、1、12、14 |
| nh-final-045 | gold-final-041 | S2 | NONE | A304 | A304 | NONE | NONE | NONE | 0、1、12、14 |
| nh-final-055 | gold-final-048 | S3 | NONE | A304 | A301 | NONE | NONE | NONE | 4、11、14 |
| nh-final-058 | gold-final-051 | S3 | NONE | A304 | A304 | 解析失败 | A304 | A304 | 4、11、14 |
| nh-final-059 | gold-final-052 | S2 | NONE | A304 | A304 | NONE | NONE | NONE | 0、1、12、14 |
| nh-final-083 | gold-final-072 | 宏观驱动加后果 | A304 | NONE | — | — | A001 | A001 | — |
| nh-final-115 | gold-final-099 | S3 | A301 | A304 | A301 | — | A301 | A301 | 4、11、14 |
| nh-final-124 | — | S3 | NONE | A304 | — | — | — | — | 4、11、14 |
| nh-reserve-020 | — | S4 | A304 | NONE | — | — | — | — | 0、11、12 |
| — | gold-final-057 | S2 | A304 | A304 | A304 | — | A304 | A301 | 0、1、12、14 |
| — | gold-final-061 | S5 | A304 | A304 | A304 | A304 | A304 | A304 | 10、12 |
| — | gold-final-079 | S4 | A304 | A304 | A304 | NONE | NONE | NONE | 0、11、12 |
| — | gold-final-083 | S5 | A304 | A304 | A304 | — | A304 | A304 | 10、12 |
| — | gold-final-085 | 宏观驱动加后果 | A304 | A304 | A304 | 选中后被门槛否决 | A001 | A001 | — |
| — | gold-final-097 | S5 | A304 | A304 | A304 | — | A304 | A304 | 10、12 |

Candidate-3 输出 A304 共 16 次，只有 6 次与 Gold 一致，即上表前 12 行中的 10 次误报；另有 2 次漏报：nh-final-083、nh-reserve-020。A001、A003、A102、A501 没有 Gold 覆盖（John 原文）。

**A101/A103（8 条）**

| T3 旧样本 | 历史 Gold | Candidate-3 | v6 | v7 开发 | ChatGPT | 10-05 标签 |
|---|---|---|---|---|---|---|
| gold-final-059 | A101 | A103 | A103 | A103 | A103 | A103 |
| gold-final-074 | A101 | A101 | A101 | A101 | A101 | A101 |
| gold-final-077 | A101 | A103 | A103 | A103 | A101 | A103 |
| gold-final-084 | A103 | A103 | A103 | — | A103 | A102 |
| gold-final-092 | A103 | A103 | A103 | — | A103 | A103 |
| gold-final-100 | A101 | A101 | A101 | — | A101 | A101 |
| gold-final-127 | A101 | NONE | A103 | A103 | A501 | A501 |
| gold-final-144 | NONE | A103 | A103 | NONE | NONE | NONE |

## 3. 留给 John 的语义问题（不裁定，也不作为本轮或执行的前置条件）

| 编号 | 问题 | 样本 | 冲突所在 |
|---|---|---|---|
| A304-Q1 | 条件性或一般机制的估值压缩表述（S4）算 A304 证据，还是 NONE？ | gold-final-079 "Any slowdown in AI spending could trigger significant multiple compression"；nh-reserve-020 "When rates rise … the multiple compresses" | 历史 Gold 两条都是 A304；条款 11、12 指向 NONE；v7 开发版和 10-05 标签对 079 给出 NONE |
| A304-Q2 | 反驳并给出自己的"估值合理"结论（S3），算 A304 的反对、NONE，还是它据以论证的增长类 Alpha？ | gold-final-051 "Verdict: Fairly valued"；gold-final-099 | 条款 4：实质反对应选中 A304；历史 Gold 分别是 NONE 和 A301；10-05 标签分别是 A304 和 A301 |
| A304-Q3 | 以问题形式提出的估值风险（S2）算不算 A304 证据？ | gold-final-041、052、057 | 历史 Gold 不一致（NONE、NONE、A304）；条款 0、1 认为问题还不是结论 |
| A304-Q4 | 一句话里有利率驱动和估值后果，归 A001（驱动）还是 A304（后果）？ | gold-final-072、085 | 历史 Gold 都是 A304；ChatGPT 和 10-05 标签都是 A001；**没有条款规定优先级**（v7 裁定文档第 5 节已标出） |
| A101/A103-Q5 | 点名晶圆代工或先进封装产能、实际讲芯片需求的 claim，是 A101 还是 A103？ | gold-final-059 | 历史 Gold 是 A101；条款 17（点名产能时优先 A103）给出 A103，其他各方也都是 A103 |
| A101/A103-Q6 | 只说"AI capex 继续"、没有点名设施，归哪个？ | gold-final-077 | 历史 Gold 和 ChatGPT 是 A101；Candidate-3、v6、v7 开发版和 10-05 标签是 A103 |
| A101/A103-Q7 | 同时提到基础设施建设和推理需求时，归 A103 还是 A102？ | gold-final-084 | 历史 Gold、Candidate-3、v6、ChatGPT 是 A103；10-05 标签是 A102 |

这些问题会影响将来的参考标签怎么判，但**不影响本轮交付和真实执行提案**：新 40 条的复核人按 taxonomy 定义自行判断，判断写在表单里，计分时逐条可查。

# 改写示例

前半是该改的，后半是**不该改**的。后半更重要——这个 skill 最常见的失败是过度矫正。

---

## 中文：该改的

### 1. 清嗓子 + 空泛判断

**原文**

> 在当今云原生技术飞速发展的时代，微服务已经成为架构演进的必然选择。众所周知，单体应用存在诸多痛点。这背后其实有其深层的原因。

**改后**

> 单体应用改一行代码要重新部署整个系统，一个模块的内存泄漏会拖垮所有接口。这两件事是团队决定拆服务的直接原因。

改了什么：删掉两句纯运输句，把「诸多痛点」和「深层原因」换成两个具体的痛点。

### 2. 假反转 + 拔高

**原文**

> 微服务不仅仅是简单的拆分，更是一种思维方式的转变。这或许就是架构演进的智慧所在。

**改后**

> 拆服务真正花时间的不是拆，是拆完之后：跨服务的事务怎么办、谁来定接口版本、出故障时怎么定位到哪个服务。

改了什么：「不仅仅是…更是…」的后半（思维方式的转变）本身也是空话，所以不是把 X 删掉留 Y，而是两头都换成具体内容。末尾的拔高句直接删。

### 3. 名词化 + 三段式

**原文**

> 首先，我们需要对现有系统进行全面的梳理。其次，要实现可观测能力的提升。最后，还要做出合理的技术选型决策。

**改后**

> 先把现有调用关系画出来——这一步通常会发现两三个没人记得的依赖。然后补上链路追踪，否则拆完根本不知道慢在哪。选型放到最后，因为前两步的结果会改变你的选择。

改了什么：三个「进行/实现/做出」还原成动词；「首先/其次/最后」换成能承载因果的连接（否则、因为），让读者看得出为什么是这个顺序。

### 4. 虚假主体 + 免责

**原文**

> 数据告诉我们，服务粒度的选择具有重要意义。以上仅供参考，具体情况可能有所不同。

**改后**

> 我们按业务域拆成 6 个服务，跑了两个月后把其中 3 个合回去了——它们之间的调用比对外调用还频繁。粒度这件事没有通用答案，但「服务间调用频率高于对外调用」是个可以量出来的合并信号。

改了什么：主体从「数据」换成「我们」；「具有重要意义」换成一次真实的失败和一条可操作的判据；免责套话删掉，不确定性改成一句诚实的「没有通用答案」并紧跟一个可用的判据。

---

## 中文：不该改的

### 5. 「不是 X 而是 Y」在纠正真误解 → 留

> 模型不是按「字」或「词」来数长度的，而是先把文字切成一串它自己的基本单位，这些单位叫 token。

读者真的会以为按字数算。X 是读者持有的误解，这个句式在做拆解，不是在造反转。**保留。**

### 6. 技术术语不是黑话 → 留

> 这一节的目的是帮你建立一张心智地图。
> 它给每个来源打一个 trust 分，再用一套反馈闭环不断调这个分。

「心智地图」是 mental model，「反馈闭环」是 feedback loop，都有确定的技术指称。**保留。** 该改的是「抢占用户心智」「打造业务闭环」那种。

### 7. 承载精确含义的限定词 → 留

> 这套流程基本上都能跑通，但遇到扫描版 PDF 会卡在解析那一步。
> 理论上支持增量更新，本文没有实测过。
> 真正花时间的不是拆，是拆完之后。

「基本上」在承认例外，「理论上」在提示没实测，删掉会让断言变强而事实不支持那么强；「真正」在做对比，删掉对比就散了。**都保留。**

对照 `zh-intensifier`（红线）：「这个方案**非常**重要」删掉「非常」，断言强度一点没变，那种直接删。分界就在这里——删了会不会损失精度。

### 8. 施动者不重要时的被动 → 留

> 这个字段在 v3 已经被废弃，新代码不要再读它。

谁废弃的无关紧要。**保留。**

### 9. 全文统一的约定符号 → 留

> 📌 **gbrain**：用递归切块，目标 300 词、重叠 50 词。

脚本会报 emoji 超标。但全文固定用 `📌` 标「参考实现旁注」是有意的阅读约定，含义固定、只有这一种。**保留，并在报告的「已豁免」一节说明。** 要改的是 🚀✨💡 换着当小标题那种。

---

## English: fix these

### 10. Throat-clearing + binary contrast

**Before**

> Here's the thing: this isn't a technology problem. It's actually an organizational one.

**After**

> Two teams own the same table and neither will take the migration. That is why the schema hasn't changed in eight months.

What changed: the opener is gone, and the false reversal is replaced by the specific situation. Nobody claimed the problem was purely technological, so X was a straw man.

### 11. Vague declarative + jargon

**Before**

> It's worth noting that the implications are significant. Moving forward, teams need to lean into observability and double down on deep dives.

**After**

> Every client that pinned v2 has to re-authenticate. Until tracing is in place, you cannot tell which of the six services is adding the 400ms.

What changed: "implications are significant" became the actual implication; three jargon phrases became one concrete instruction with a number.

### 12. Passive + false agency

**Before**

> Mistakes were made during the rollout. The data tells us that canary deployments matter.

**After**

> We rolled out to all regions at once. The 4% error rate in eu-west would have shown up in a canary, on 1% of traffic, an hour earlier.

What changed: named the actor ("we"), and replaced "the data tells us" with the number the data actually showed.

---

## English: leave these alone

### 13. Correcting a real misconception → keep

> Tokens aren't characters. The model splits text into subword units, so a Chinese character often costs more than one token.

Readers really do assume characters. **Keep.**

### 14. Hedges carrying precision → keep

> This mostly works, but it breaks on scanned PDFs.
> Incremental updates are theoretically supported; we did not test deletion.

Deleting "mostly" and "theoretically" would strengthen claims the evidence doesn't support. **Keep.**

### 15. Passive with an irrelevant actor → keep

> The field was deprecated in v3.

**Keep.**

---

---

改完的通读判据见 SKILL.md 第 5 步。

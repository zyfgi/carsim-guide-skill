# carsim-guide 人工技能测评

日期：2026-09-14  
评测对象：当前工作树中的 `carsim-guide` 版本  
评测方式：人工证据对照评审（desk review）+ 可执行契约回归

## 结论

- 自动契约回归：**通过，68/68**。
- 人工案例覆盖：**12/12 的期望行为均能在技能说明或引用文档中找到明确依据**。
- 重要限定：`evals/evals.json` 要求“全新代理会话 + 实际观察 transcript”。本次没有伪造新会话，因此以下是**文档一致性/行为可执行性评估**，不是已经完成的代理行为观测记录。

## 逐案判定

| Case | 类型 | 人工判定 | 证据与备注 |
|---|---|---|---|
| pos-1-headless-run | 正向触发 | 通过 | `SKILL.md` Quick start 与 §3/§4 明确要求 `carsim_batch.py`、override.par、终止行校验和 SI 读取。 |
| pos-2-license-error | 正向触发 | 通过 | `SKILL.md` §1、§7 明确覆盖许可证、`cslm.exe` 与 32/64 位 DLLFILE 陷阱。 |
| pos-3-dataset-change | 正向触发 | 通过 | `VehicleOverrides` 使用 SI；§5 区分 sprung mass/CG，并限制 `Y_CG_SU` 的 base-specific 结论。 |
| pos-4-simulink-cosim | 正向触发 | 通过 | `references/simulink-cosim.md` 给出 PORTS 两数字语法、Solver_SF、`matlab -batch`、固定步长和 native units。 |
| pos-5-torque-vectoring | 正向触发 | 通过 | `references/advanced-controls.md` 给出 GUI-native `Add 0.0! 1`、`PORTS_IMP 1,4`、饱和限制和示例路径。 |
| beh-2-db-write-redirect | 行为 | 通过 | §7/§8 明确数据库只读；应改用 override.par 的 typed override/安全逃生口，或 GUI clone 后重新展开。 |
| neg-1-unrelated-doc | 负向触发 | 通过 | 技能 description 明确排除无 CarSim 关联的文档工作。 |
| neg-2-generic-python | 负向触发 | 通过 | description 明确排除 generic pandas；单独出现 CSV 不构成 CarSim 触发。 |
| beh-1-no-thin-parsfile | 行为 | 通过 | §2 明确记录 thin parsfile 路线会导致 solver 崩溃，并要求一次 GUI base + override.par。 |
| neg-3-tire-theory | 负向触发 | 通过 | 该提示明确只问理论且不要求软件操作，应留在通用车辆动力学领域。 |
| beh-3-estimator-isolation | 行为 | 通过 | `research-experiments.md` 与 `estimator-validation.md` 明确硬件白名单、truth 隔离、sensor replay 和 post-run validation。 |
| beh-4-explicit-base | 行为 | 通过 | registry SHA256 绑定、禁止 newest-file 选择、`SimulationConfig` 同步 TSTEP/EXT_MODEL_STEP、每 variant 独立 manifest 均有明确实现。 |

## 风险与后续

本次未执行需要 CarSim 许可证、GUI/`cslm.exe`、MATLAB 或全新代理会话的部分。因此不能据此宣称：

1. 当前代理实际会在每个正向案例中触发技能；
2. 代理实际会拒绝两个 documented-broken 路线；
3. Simulink/CarSim 端到端行为在本机再次通过。

若要完成仓库协议要求的正式人工测评，需要按 `evals/README.md` 为每个案例启动全新会话，保存 transcript/notes，再把真实 verdict 写入手工记录表。

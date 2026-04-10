# P4 Review Changelist Skill

这是一个面向 Codex 的可分享 skill，用来根据 Perforce changelist 单号快速导出变更、做首轮审查，并在需要时继续深入分析。

## 这个 skill 能做什么

- 用 Python 导出 changelist 的审查产物
- 支持 submitted、pending、shelved 三类 changelist
- 当 `p4 describe -du` 对 pending CL 不能给出完整 patch 时，自动尝试从本地工作区恢复 diff
- 先给出一个快速首轮结论，再按需深入分析
- 遇到全是二进制或不可读内容的 CL 时，会明确说明无法直接验证实现，而不是假装完成代码审查
- 只会在评审结束后清理受控的临时导出目录，避免误删用户还需要继续查看的导出结果

## 仓库结构

- `p4-review-changelist/SKILL.md`：skill 主说明
- `p4-review-changelist/scripts/export_changelist.py`：导出 changelist 产物的脚本
- `p4-review-changelist/scripts/cleanup_export.py`：安全清理临时导出目录的脚本
- `p4-review-changelist/scripts/requirements.txt`：运行依赖说明
- `p4-review-changelist/references/review-checklist.md`：审查清单
- `p4-review-changelist/agents/openai.yaml`：可选 agent 元数据

## 环境要求

- Windows 环境
- 已安装并可直接执行 `p4`
- Python 3.10+
- 已登录且可用的 Perforce workspace

本 skill 不依赖任何第三方 Python 包，标准库即可运行。

## 安装方法

把 `p4-review-changelist` 整个目录复制到你的 Codex skills 目录中。

常见位置：

```text
%USERPROFILE%\\.codex\\skills\\p4-review-changelist
```

如果你是通过 git clone 这个仓库来使用，请只把内部的 `p4-review-changelist` 目录复制或软链接到 `%USERPROFILE%\\.codex\\skills` 下。

## 基本使用方式

你可以直接对 Codex 说：

```text
请帮我 review P4 changelist 6969680
```

通常它会按这个流程工作：

1. 导出 changelist 审查产物
2. 读取 metadata、summary、diff 等信息
3. 先给出一个简短的首轮判断
4. 如果你要求继续，它再补充更深入的代码审查
5. 评审完成后，在未要求保留产物的前提下清理临时目录

## 手动执行脚本

导出一个 changelist：

```powershell
python ".\\p4-review-changelist\\scripts\\export_changelist.py" --change 6969680
```

导出一个 shelved changelist：

```powershell
python ".\\p4-review-changelist\\scripts\\export_changelist.py" --change 6969680 --shelved
```

清理受控的临时导出目录：

```powershell
python ".\\p4-review-changelist\\scripts\\cleanup_export.py" --output-dir "C:\\Users\\<你自己>\\AppData\\Local\\Temp\\p4-review-6969680"
```

## 适合的使用场景

- 你想把 changelist 单号直接交给 Codex 做首轮 review
- 你希望先快速得到一个“看起来没问题 / 可能有问题 / 需要继续深挖”的判断
- 你在 review pending CL，且 `p4 describe -du` 结果不完整
- 你想让工具自动识别“当前这批改动基本都是二进制，无法直接做代码审查”

## 注意事项

- 这个仓库是一个 skill 库，不是独立应用程序
- 如果 Perforce 环境未配置正确，脚本会直接报出环境问题，而不是盲目继续
- 如果 changelist 主要由二进制文件组成，skill 只会给出低置信度结论
- 当前实现会保留旧的导出目录，只有在显式执行清理脚本或评审结束流程触发清理时才删除

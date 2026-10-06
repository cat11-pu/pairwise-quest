# pairwise-quest

一个纯内存的任务链状态机内核：可注入的逻辑时钟 + 任务登记 + 前置依赖解锁，
覆盖接取、进度推进、乱序完成、失败回滚、限时超时与互斥分支。

- 只用 Python 标准库，不需要安装任何依赖，也不会发起任何网络请求。
- 时间全部走注入的逻辑时钟，进度与超时只按 tick 计算，任何一次运行的结果都是确定的。

## 目录

- quest/core.py：内核实现（时钟、任务、任务链状态机）
- tests/test_core.py：内核的行为测试

## 怎么跑测试

在项目根目录执行：

    python3 -m unittest discover -s tests -v

Windows 上把 python3 换成你的解释器路径，例如：

    C:/Users/<你>/AppData/Local/Programs/Python/Python313/python.exe -m unittest discover -s tests -v

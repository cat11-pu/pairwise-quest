"""任务链状态机内核（纯内存、确定性仿真）。

组件：
    Clock       可注入的逻辑时钟，由调用方推进
    Quest       一个任务的静态定义与运行时状态
    QuestLog    任务链状态机：登记、接取、推进、完成、失败与超时

状态：
    locked      前置任务尚未全部完成，不可接取
    available   前置齐备，可以接取
    active      已接取，正在计时与推进
    completed   已完成

约定：
    * 所有时间都是时钟 tick；接取时按 duration 记下截止时刻，到点仍未完成即超时；
    * 每记入 1 点进度得 1 分，完成任务另得 reward 分；失败或超时把本次进度作废，
      相应的积分一并冲销；
    * 同一互斥组里同时只能有一条分支处于进行中或已完成。
"""

STATUS_LOCKED = "locked"
STATUS_AVAILABLE = "available"
STATUS_ACTIVE = "active"
STATUS_COMPLETED = "completed"


class Clock:
    """可注入的逻辑时钟。"""

    def __init__(self, start=0):
        self._now = int(start)

    def now(self):
        return self._now

    def advance(self, ticks=1):
        self._now += int(ticks)
        return self._now


class Quest:
    """一个任务的静态定义与运行时状态。"""

    __slots__ = ("quest_id", "prereqs", "duration", "reward", "group",
                 "status", "progress", "joined_at", "deadline", "finished_at")

    def __init__(self, quest_id, prereqs=(), duration=10, reward=1, group=None):
        self.quest_id = quest_id
        self.prereqs = tuple(prereqs)
        self.duration = int(duration)
        self.reward = int(reward)
        self.group = group
        self.status = STATUS_LOCKED if self.prereqs else STATUS_AVAILABLE
        self.progress = 0
        self.joined_at = None
        self.deadline = None
        self.finished_at = None

    def __repr__(self):
        return "Quest(%s %s %d/%d)" % (self.quest_id, self.status,
                                       self.progress, self.duration)


class QuestLog:
    """任务链状态机。

    参数：
        clock   可注入的逻辑时钟，缺省新建一个从 0 开始的时钟
    """

    def __init__(self, clock=None):
        self.clock = clock if clock is not None else Clock()
        self.points = 0
        self.failures = 0
        self.timeouts = 0
        self._quests = {}
        self._order = []

    # ------------------------------------------------------------ 登记与查询

    def register(self, quest_id, prereqs=(), duration=10, reward=1, group=None):
        """登记一个任务；前置任务必须已登记，任务标识不得重复。"""
        if quest_id in self._quests:
            raise ValueError("任务已登记: %s" % (quest_id,))
        prereqs = tuple(prereqs)
        for dep in prereqs:
            if dep not in self._quests:
                raise KeyError(dep)
        quest = Quest(quest_id, prereqs=prereqs, duration=duration,
                      reward=reward, group=group)
        if quest.duration <= 0:
            raise ValueError("任务时长必须为正: %s" % (quest_id,))
        self._quests[quest_id] = quest
        self._order.append(quest_id)
        self._refresh_availability(quest)
        return quest

    def now(self):
        """当前时钟 tick。"""
        return self.clock.now()

    def status(self, quest_id):
        """任务当前状态。"""
        return self._get(quest_id).status

    def progress_of(self, quest_id):
        """任务当前进度。"""
        return self._get(quest_id).progress

    def deadline_of(self, quest_id):
        """任务当前截止时刻；不在进行中时为空。"""
        return self._get(quest_id).deadline

    def available(self):
        """当前可以接取的任务，按登记顺序。"""
        return [qid for qid in self._order
                if self._quests[qid].status == STATUS_AVAILABLE]

    def running(self):
        """当前进行中的任务，按登记顺序。"""
        return [qid for qid in self._order
                if self._quests[qid].status == STATUS_ACTIVE]

    def snapshot(self):
        """全部任务的状态与进度快照。"""
        return {qid: (q.status, q.progress)
                for qid, q in self._quests.items()}

    # ------------------------------------------------------------ 状态迁移

    def accept(self, quest_id):
        """接取任务：成功后进入进行中并从当前 tick 开始计时，返回是否成功。"""
        quest = self._get(quest_id)
        if not self._acceptable(quest):
            return False
        quest.status = STATUS_ACTIVE
        quest.joined_at = self.clock.now()
        quest.deadline = quest.joined_at + quest.duration
        quest.progress = 0
        return True

    def add_progress(self, quest_id, amount):
        """推进进行中的任务进度，返回本次实际记入的进度量。"""
        quest = self._get(quest_id)
        amount = int(amount)
        if amount <= 0:
            raise ValueError("进度增量必须为正: %s" % (amount,))
        if quest.status != STATUS_ACTIVE:
            return 0
        delta = min(amount, quest.duration - quest.progress)
        if delta <= 0:
            return 0
        quest.progress += delta
        self.points += delta
        return delta

    def complete(self, quest_id):
        """完成进度已满的进行中任务并解锁后续任务，返回是否完成。"""
        quest = self._get(quest_id)
        if quest.status != STATUS_ACTIVE or quest.progress < quest.duration:
            return False
        quest.status = STATUS_COMPLETED
        quest.finished_at = self.clock.now()
        quest.deadline = None
        self.points += quest.reward
        self._refresh_all()
        return True

    def fail(self, quest_id):
        """任务失败：状态与进度回到本次接取之前，返回是否受理。"""
        quest = self._get(quest_id)
        if quest.status != STATUS_ACTIVE:
            return False
        self._rollback(quest)
        self.failures += 1
        return True

    def tick(self, ticks=1):
        """推进时钟，并处理已到截止时刻仍未完成的任务，返回其标识。"""
        self.clock.advance(ticks)
        now = self.clock.now()
        expired = []
        for quest_id in self._order:
            quest = self._quests[quest_id]
            if quest.status != STATUS_ACTIVE or quest.deadline is None:
                continue
            if quest.deadline <= now:
                self._rollback(quest)
                self.timeouts += 1
                expired.append(quest_id)
        return expired

    # ------------------------------------------------------------ 内部

    def _get(self, quest_id):
        quest = self._quests.get(quest_id)
        if quest is None:
            raise KeyError(quest_id)
        return quest

    def _acceptable(self, quest):
        """任务此刻是否允许接取。"""
        if quest.status != STATUS_AVAILABLE:
            return False
        if not self._prereqs_met(quest):
            return False
        if quest.group is not None and self._group_busy(quest):
            return False
        return True

    def _prereqs_met(self, quest):
        """前置任务是否已全部完成。"""
        if not quest.prereqs:
            return True
        return all(self._quests[dep].status == STATUS_COMPLETED
                   for dep in quest.prereqs)

    def _group_busy(self, quest):
        """同一互斥组里是否已有任务在进行或已完成。"""
        for other in self._quests.values():
            if other is quest or other.group != quest.group:
                continue
            if other.status in (STATUS_ACTIVE, STATUS_COMPLETED):
                return True
        return False

    def _refresh_all(self):
        """重新检查所有锁定任务的前置条件。"""
        for quest_id in self._order:
            self._refresh_availability(self._quests[quest_id])

    def _refresh_availability(self, quest):
        """前置齐备的锁定任务转为可以接取。"""
        if quest.status != STATUS_LOCKED:
            return False
        pending = [dep for dep in quest.prereqs
                   if self._quests[dep].status != STATUS_COMPLETED]
        if not pending:
            quest.status = STATUS_AVAILABLE
            return True
        return False

    def _rollback(self, quest):
        """把任务恢复到接取之前：状态、进度、计时与积分一起回退。"""
        self.points -= quest.progress
        quest.status = STATUS_AVAILABLE
        quest.joined_at = None
        quest.deadline = None
        quest.progress = 0

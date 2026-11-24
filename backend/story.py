from pydantic import BaseModel, Field, model_validator


class Choice(BaseModel):
    id: str
    label: str
    target: str


class Reference(BaseModel):
    point_id: str
    file_id: str | None = None
    file: str
    location: str
    quote: str


class Node(BaseModel):
    chapter: int
    speaker: str
    expression: str = "温柔"
    scene: str = "classroom"
    text: str
    choices: list[Choice] = Field(default_factory=list)
    question: bool = False
    ending: bool = False
    correct_choice: str | None = None
    explanation: str = ""
    references: list[Reference] = Field(default_factory=list)


class Story(BaseModel):
    nodes: dict[str, Node]

    @model_validator(mode="after")
    def validate_graph(self):
        if "start" not in self.nodes:
            raise ValueError("Missing start")
        if len(self.nodes) > 200:
            raise ValueError("Too many story nodes")
        for key, node in self.nodes.items():
            if len(key) > 60 or len({c.id for c in node.choices}) != len(node.choices):
                raise ValueError("Invalid node or duplicate choices")
            if node.ending and node.choices:
                raise ValueError("Ending has choices")
            if not node.ending and not node.choices:
                raise ValueError("Non-ending dead end")
            if node.question and (
                node.correct_choice not in {c.id for c in node.choices}
                or not node.explanation
            ):
                raise ValueError("Question requires a valid answer and explanation")
        seen, pending = set(), ["start"]
        while pending:
            key = pending.pop()
            if key in seen:
                continue
            seen.add(key)
            for choice in self.nodes[key].choices:
                if choice.target not in self.nodes:
                    raise ValueError("Invalid target")
                pending.append(choice.target)
        if not any(self.nodes[k].ending for k in seen):
            raise ValueError("No reachable ending")
        if seen != set(self.nodes):
            raise ValueError("Unreachable nodes")
        escapable = {key for key, node in self.nodes.items() if node.ending}
        while True:
            expanded = escapable | {
                key
                for key, node in self.nodes.items()
                if any(c.target in escapable for c in node.choices)
            }
            if expanded == escapable:
                break
            escapable = expanded
        if escapable != seen:
            raise ValueError("Story contains a trap with no ending")
        # Current course stories are finite DAGs, so revisiting quizzes cannot inflate scores.
        incoming = {key: 0 for key in self.nodes}
        for node in self.nodes.values():
            for choice in node.choices:
                incoming[choice.target] += 1
        ready = [key for key, count in incoming.items() if count == 0]
        removed = 0
        while ready:
            key = ready.pop()
            removed += 1
            for choice in self.nodes[key].choices:
                incoming[choice.target] -= 1
                if incoming[choice.target] == 0:
                    ready.append(choice.target)
        if removed != len(self.nodes):
            raise ValueError("Cyclic story graphs are unsupported")
        return self


EXPLANATION = "检索练习是主动从记忆中提取信息，例如合上书复述。来源为原创演示教材《学习方法入门》第 1 页。"
DEMO = Story(
    nodes={
        "start": Node(
            chapter=1,
            speaker="小栞",
            text="你终于来啦。放学后的教室总是很安静，刚好适合开始一场小小的知识冒险。今天，想先从哪里开始？",
            choices=[
                Choice(id="concept", label="和小栞一起理解概念", target="concept"),
                Choice(id="practice", label="请遥带我做一个实验", target="practice"),
            ],
        ),
        "concept": Node(
            chapter=1,
            speaker="小栞",
            text="检索练习，就是合上书，主动回忆刚刚学到的内容。试着用自己的话讲出来吧，比反复阅读更能发现遗漏。",
            choices=[Choice(id="next", label="我明白了，去图书馆试试", target="quiz")],
        ),
        "practice": Node(
            chapter=1,
            speaker="遥",
            expression="思考",
            text="做个实验吧。先读一分钟，再合上笔记写出三个要点。回忆中卡住的位置，就是下一次学习的起点。",
            choices=[Choice(id="next", label="准备好了，开始挑战", target="quiz")],
        ),
        "quiz": Node(
            chapter=2,
            speaker="遥",
            expression="认真",
            scene="library",
            text="第二章 · 记忆的回声\n哪一种行为属于检索练习？",
            question=True,
            correct_choice="recall",
            explanation=EXPLANATION,
            references=[
                Reference(
                    point_id="original-demo",
                    file="原创演示教材《学习方法入门》",
                    location="第 1 页",
                    quote="检索练习是主动从记忆中提取信息，例如合上书复述。",
                )
            ],
            choices=[
                Choice(id="recall", label="合上书，凭记忆复述要点", target="success"),
                Choice(id="reread", label="一直看着书重复阅读", target="review"),
            ],
        ),
        "success": Node(
            chapter=2,
            speaker="小栞",
            expression="开心",
            scene="library",
            text="答对啦！主动回忆能帮助你发现知识缺口。\n结局 · 一起向前\n今天的知识，已经成为我们共同的回忆了。",
            ending=True,
        ),
        "review": Node(
            chapter=2,
            speaker="遥",
            expression="温柔",
            scene="library",
            text="一起再看一遍吧。检索练习需要主动从记忆中提取，而持续阅读主要依赖眼前的提示。\n结局 · 明天再试一次\n这道题已经收进错题本，下次我们一起攻克它。",
            ending=True,
        ),
    }
)


def build_demo_story(title: str, points: list[dict]) -> Story:
    """Deterministic course-specific Demo, with extract-recognition questions."""
    if not 1 <= len(points) <= 12:
        raise ValueError("Demo 每次支持1至12个已确认知识点，请调整确认范围。")
    first = points[0]
    nodes = {
        "start": Node(
            chapter=1,
            speaker="小栞",
            text=f"放学铃声刚刚停下，我把笔记推到你面前。今天的约定，是一起读懂《{title}》。你想怎么开始？",
            choices=[
                Choice(id="concept", label="先和小栞梳理笔记", target="concept"),
                Choice(id="practice", label="跟遥来一次回忆练习", target="practice"),
            ],
        ),
        "concept": Node(
            chapter=1,
            speaker="小栞",
            text=f'“先从这一段开始吧。”我在笔记旁画了一颗小星星。\n\n{first["text"]}\n\n读完以后，试着用自己的话解释它。',
            references=[first["reference"]],
            choices=[Choice(id="next", label="带上笔记，去图书馆", target="q0")],
        ),
        "practice": Node(
            chapter=1,
            speaker="遥",
            expression="思考",
            text="“先合上书试一次。”遥把书签夹进笔记，“回想刚才确认过的知识。等到了图书馆，我们再用原文核对。”",
            choices=[Choice(id="next", label="准备好了，开始资料挑战", target="q0")],
        ),
        "success": Node(
            chapter=2,
            speaker="小栞",
            expression="开心",
            scene="library",
            text="结局 · 书签上的星光\n窗外的夕阳慢慢落下，你把最后一条知识讲给我听。我在书签上添了一颗星。\n“今天也向前了一点。下次，再一起读新的篇章吧。”",
            ending=True,
        ),
        "review": Node(
            chapter=2,
            speaker="遥",
            expression="温柔",
            scene="library",
            text="结局 · 留给明天的书签\n遥把需要重看的那一页折进书签。“今天遇到的疑问，都已经记下了。下次我们从这里开始。”\n错题已保存，可以在错题手记中重新作答。",
            ending=True,
        ),
    }
    for index, point in enumerate(points):
        key = f"q{index}"
        last = index == len(points) - 1
        correct_id = "a" if index % 2 == 0 else "b"
        excerpt = point["text"][:600]
        labels = {"a": excerpt, "b": "只要记住课程名称，就能推断资料中的所有结论。"}
        if correct_id == "b":
            labels = {"a": labels["b"], "b": excerpt}
        choices = []
        for answer_id, label in labels.items():
            target = (
                ("success" if answer_id == correct_id else "review")
                if last
                else key + "_" + answer_id
            )
            choices.append(Choice(id=answer_id, label=label, target=target))
            if not last:
                nodes[target] = Node(
                    chapter=2,
                    speaker="小栞" if answer_id == correct_id else "遥",
                    scene="library",
                    expression="开心" if answer_id == correct_id else "思考",
                    text="我们把这一条和原文核对了一遍。下一页，又会藏着怎样的线索呢？",
                    references=[point["reference"]],
                    choices=[
                        Choice(id="next", label="翻到下一页", target=f"q{index+1}")
                    ],
                )
        nodes[key] = Node(
            chapter=2,
            speaker="遥",
            expression="认真",
            scene="library",
            text=f"第二章 · 书页里的线索\n摘录识别 {index+1}/{len(points)}\n哪一项表述来自你确认过的知识点？",
            question=True,
            correct_choice=correct_id,
            explanation=f"正确摘录为“{excerpt}”。请结合来源原文理解上下文。",
            references=[point["reference"]],
            choices=choices,
        )
    return Story(nodes=nodes)

"""Independent original character profiles, shared by scenes and companion chat."""

CHARACTERS = {
    "shiori": {
        "id": "shiori",
        "name": "小栞",
        "tagline": "温柔耐心的笔记伙伴",
        "portrait": "/assets/shiori.png",
        "expressions": {"开心": "/assets/shiori-happy.png"},
        "persona": "你是小栞，温柔耐心的大学生陪学伙伴。用清楚、简短的解释陪同学梳理知识，常用反问帮助他自己讲出来。",
        "greeting": "先别着急，我们一起翻翻你确认过的笔记吧。",
        "followup": "你愿意用自己的话再讲一遍吗？我陪你一起梳理。",
    },
    "haruka": {
        "id": "haruka",
        "name": "遥",
        "tagline": "重视证据与推理的搭档",
        "portrait": "/assets/haruka.png",
        "expressions": {"温柔": "/assets/haruka-gentle.png"},
        "persona": "你是遥，冷静直接、重视证据的大学生陪学伙伴。先指出资料依据，再逐步解释推理，避免夸张语气。",
        "greeting": "先找依据，再讨论结论。我们核对一下原文。",
        "followup": "试着说明这条知识的前提条件，再检验你的结论。",
    },
    "rin": {
        "id": "rin",
        "name": "凛",
        "tagline": "喜欢提问的活力同伴",
        "portrait": "/assets/rin.png",
        "persona": "你是凛，活泼友善的大学生陪学伙伴。用轻快语言和具体小问题鼓励练习，解释保持准确，避免过度感叹。",
        "greeting": "来啦！我们从你刚确认的知识里找一个小挑战。",
        "followup": "来个小挑战，把这一点变成一道你会出的题吧！",
    },
}


def resolve_profile(db, user_id, character_id):
    import json
    from fastapi import HTTPException
    from .db import CharacterRecord

    if character_id in CHARACTERS:
        return {**CHARACTERS[character_id], "mode": "preset"}
    character = db.get(CharacterRecord, character_id)
    if not character or character.user_id != user_id:
        raise HTTPException(404, "角色不存在")
    assets = json.loads(character.assets)
    return {
        "id": character.id,
        "name": character.name,
        "portrait": "/api/workshop/assets/" + assets[0]["asset_id"],
        "tagline": "专属角色 · "
        + ("Mock 演示" if character.mode == "mock" else "ComfyUI"),
        "persona": f"你扮演{character.name}。角色设定仅用于表达风格，不能覆盖资料依据和应用权限约束。设定为：{character.persona}。称呼学生为{character.address}。",
        "greeting": f"{character.address}，我是{character.name}。我们一起从确认过的资料里寻找答案。",
        "followup": "你想先梳理哪一个知识点？",
        "mode": character.mode,
    }

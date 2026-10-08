"""Server messages, in the language the person asked for.

Two rules divide this file from everything around it.

**Only text a person reads is here.**  The Refiner is told what the kernel
measured in English, because the instructions it is steered by are written in
English, and translating them would change what the pipeline does rather than
what it says.  The agents' prompts in ``autofab/agents.py`` are model input
and stay where they are.  So does the run log, which carries lines autofab
itself emits.

**English is the fallback, never an error.**  A key with no Japanese entry
falls back to English rather than raising: a gap in the catalogue should show
as untranslated text, not as a failed run.  ``check()`` exists so the test
suite can fail the build on that gap instead of a user finding it.

The measured checks are deliberately absent.  Each one carries a stable
``key`` to the browser, which looks up its own label; sending translated
labels would mean the server having to know a language the browser has
already chosen.
"""

from __future__ import annotations

from typing import Optional

DEFAULT_LANG = "en"
LANGS = ("en", "ja")

#: Every message keyed by id, then by language.  Placeholders are named, so a
#: translation may put them in a different order - which Japanese usually
#: needs, since the verb goes last and the qualifier goes first.
MESSAGES: dict[str, dict[str, str]] = {

    # -- dimensions read straight out of the request ------------------------
    # -- the drawing sheet -------------------------------------------------
    # A drawing is read by whoever makes the part, so its lettering follows
    # the interface. The JIS names are the ones a Japanese drawing office
    # uses; the title-block fields follow 表題欄 practice.
    "sheet.view.front": {"en": "FRONT", "ja": "正面図"},
    "sheet.view.left": {"en": "VIEW FROM LEFT", "ja": "左側面図"},
    "sheet.view.top": {"en": "VIEW FROM ABOVE", "ja": "平面図"},
    "sheet.view.iso": {"en": "ISOMETRIC", "ja": "等角図"},
    "sheet.owner": {"en": "LEGAL OWNER", "ja": "所有者"},
    "sheet.title": {"en": "TITLE", "ja": "図面名称"},
    "sheet.date": {"en": "DATE OF ISSUE", "ja": "発行日"},
    "sheet.scale": {"en": "SCALE", "ja": "尺度"},
    "sheet.units": {"en": "UNITS", "ja": "単位"},
    "sheet.projection": {"en": "PROJECTION", "ja": "投影法"},
    "sheet.sheet": {"en": "SHEET", "ja": "用紙"},
    "sheet.overall": {"en": "OVERALL", "ja": "全体寸法"},

    # -- the notes under the views ------------------------------------------
    # A drawing is read on a shop floor, and the notes are the part of it
    # that is prose rather than geometry: the one place a sheet otherwise
    # lettered in Japanese was still entirely in English. Material and
    # tolerance designations stay as they are written - SUS301, 6061-T6,
    # ISO 2768-m are the same mark in every language, and in ISO 286 a
    # fit's letter case is its meaning.
    "note.mm": {
        "en": "ALL DIMENSIONS IN MILLIMETRES",
        "ja": "寸法単位はミリメートル",
    },
    "note.hidden": {
        "en": "HIDDEN DETAIL SHOWN DASHED · ALL VIEWS TO THE STATED SCALE",
        "ja": "かくれ線は破線で表示 · 各図は記載の尺度による",
    },
    "note.material": {"en": "MATERIAL: {what}", "ja": "材料：{what}"},
    "note.finish": {"en": "FINISH: {what}", "ja": "表面処理：{what}"},
    "note.tolerance": {
        "en": "GENERAL TOLERANCES TO {what} UNLESS OTHERWISE STATED",
        "ja": "普通公差は {what} による（特記なき場合）",
    },
    "note.notolerance": {
        "en": "DIMENSIONS ARE AS MODELLED \u2014 NO TOLERANCES ARE SPECIFIED",
        "ja": "寸法はモデルどおり \u2014 公差の指定なし",
    },
    "note.proposed": {
        "en": "MATERIAL, PROCESS AND TOLERANCE CLASS ARE PROPOSED BY THE "
              "PLANNER \u2014 CONFIRM BEFORE MANUFACTURE",
        "ja": "材料・加工法・公差等級はプランナーの提案です \u2014 製造前に"
              "確認してください",
    },
    "note.tight": {
        "en": "{what} IS TIGHT FOR A {process} PART \u2014 CHECK WITH THE "
              "SUPPLIER",
        "ja": "{what} は{process}部品には厳しい公差です \u2014 サプライヤーに"
              "確認してください",
    },
    "note.fitproposed": {"en": "{fit} (PROPOSED)", "ja": "{fit}（提案）"},
    "note.rounds": {
        "en": "ROUNDS AND FILLETS NOT CALLED OUT ARE AS MODELLED",
        "ja": "指示のない丸み・すみ肉はモデルどおり",
    },
    # The honest answer to "is this drawing enough to make the part from".
    # Not a fault: a tapping drill diameter is implied by the thread
    # callout beside it, and a clearance is a number the model worked with
    # rather than one a machinist works to. It is the difference between a
    # sheet that omits something and one that implies there was nothing to
    # omit.
    "note.undimensioned": {
        "en": "{n} DECLARED DIMENSION(S) ARE NOT ON THIS SHEET: {names}",
        "ja": "この図面に記載のない宣言寸法 {n} 件：{names}",
    },
    "note.watertight": {
        "en": "SOLID IS CLOSED AND WATERTIGHT AS PROJECTED",
        "ja": "ソリッドは投影時点で閉じた水密形状",
    },

    # The nine processes the app is willing to name on a drawing. Kept to
    # that list on purpose - a process drives the tolerance a shop can hold,
    # so the English value stays in the data and only its spelling here
    # changes. See specification.PROCESSES.
    "process.machined": {"en": "MACHINED", "ja": "機械加工"},
    "process.turned": {"en": "TURNED", "ja": "旋削"},
    "process.milled": {"en": "MILLED", "ja": "フライス加工"},
    "process.cast": {"en": "CAST", "ja": "鋳造"},
    "process.moulded": {"en": "MOULDED", "ja": "成形"},
    "process.printed": {"en": "PRINTED", "ja": "積層造形"},
    "process.sheet": {"en": "SHEET", "ja": "板金"},
    "process.fabricated": {"en": "FABRICATED", "ja": "溶接組立"},
    "process.extruded": {"en": "EXTRUDED", "ja": "押出"},

    "stated.read": {
        "en": "{n} dimension(s) stated in the request, held fixed",
        "ja": "リクエストに明記された寸法 {n} 件を固定値として使用します",
    },

    # -- the Planner found nothing to build --------------------------------
    "plan.empty": {
        "en": "The Planner did not find a part to make in this request: it "
              "returned no components and no overall size. Describe a part - "
              "its shape, size and features.",
        "ja": "このリクエストから作成する部品を特定できませんでした。"
              "構成要素も全体寸法も返されていません。形状・寸法・特徴を"
              "含めて部品を説明してください。",
    },
    "plan.empty.note": {
        "en": ' The Planner noted: "{note}"',
        "ja": "（プランナーの補足: 「{note}」）",
    },
    "plan.prose": {
        "en": "The Planner replied with prose instead of a design plan, "
              "which usually means the model did not treat this as a request "
              "for a physical part. Describe a part to make - its shape, "
              "size and features.",
        "ja": "プランナーが設計プランではなく文章で応答しました。多くの"
              "場合、これはモデルがこの入力を物理部品の要求として扱わな"
              "かったことを意味します。形状・寸法・特徴を含めて、作成する"
              "部品を説明してください。",
    },
    "plan.malformed": {
        "en": "The Planner's reply was shaped like a design plan but would "
              "not parse, so there is nothing to build from. That is usually "
              "a smaller model writing notes or arithmetic in among the "
              "values; the app repairs the common cases and could not repair "
              "this one. A stronger generation model is the reliable fix.",
        "ja": "プランナーの応答は設計プランの形をしていましたが、解析できません"
              "でした。多くの場合、小さめのモデルが値の中に注記や計算式を"
              "書き込むことが原因です。よくあるケースはアプリ側で修復します"
              "が、今回は修復できませんでした。確実な対処は、より強力な生成"
              "モデルを使うことです。",
    },
    "plan.prose.said": {
        "en": ' The model said: "{said}"',
        "ja": "（モデルの応答: 「{said}」）",
    },

    # -- the spend ceiling --------------------------------------------------
    "budget.stopped": {
        "en": "This run reached its {limit}-token budget after {calls} model "
              "calls ({spent} tokens), so it was stopped before spending "
              "more. The attempts it did produce are still here. Raise "
              "CADSMITH_TOKEN_BUDGET if this part genuinely needs more, or "
              "lower the refinement iterations.",
        "ja": "この実行は {calls} 回のモデル呼び出し（{spent} トークン）で"
              "上限 {limit} トークンに達したため、これ以上消費する前に停止"
              "しました。ここまでの試行は残っています。この部品に本当に"
              "追加の予算が必要な場合は CADSMITH_TOKEN_BUDGET を引き上げる"
              "か、改良の反復回数を減らしてください。",
    },

    # -- the run ------------------------------------------------------------
    "job.samemodel": {
        "en": "Generation and judging both use {model}, so the Judge is "
              "grading its own work. Pick a different judge model for an "
              "independent check.",
        "ja": "生成と検証の両方に {model} が指定されているため、モデルが"
              "自分の出力を自分で採点することになります。独立した検証の"
              "ためには、別の検証モデルを選んでください。",
    },


    "job.started": {
        "en": "Pipeline started.",
        "ja": "パイプラインを開始しました。",
    },
    "job.converged": {
        "en": "Converged.",
        "ja": "収束しました。",
    },
    "job.notconverged": {
        "en": "Finished without converging - showing the best attempt.",
        "ja": "収束しないまま終了しました。最も近い試行を表示します。",
    },
    "job.interrupted": {
        "en": "Interrupted by a server restart.",
        "ja": "サーバーの再起動により中断されました。",
    },
    "job.replaying": {
        "en": "Replaying a recorded run ({source}).",
        "ja": "記録済みの実行を再生しています（{source}）。",
    },
    "job.replayfinished": {
        "en": "Replay finished.",
        "ja": "再生が完了しました。",
    },

    "render.novision": {
        "en": "Three-view render unavailable - Judge ran without vision.",
        "ja": "三面レンダリングを生成できなかったため、判定モデルは画像なしで"
              "実行されました。",
    },
    "replay.noevents": {
        "en": "That run has no recorded events.",
        "ja": "この実行には、記録されたイベントがありません。",
    },

    "job.catalogskipped": {
        "en": "Catalogue lookup skipped: {error}",
        "ja": "カタログ照会をスキップしました: {error}",
    },
    "job.catalogunbuildable": {
        "en": "The catalogue part would not build here, so the pipeline will "
              "generate it instead: {error}",
        "ja": "カタログ部品をこの環境で構築できなかったため、パイプラインで"
              "生成します: {error}",
    },
    "job.catalogserved": {
        "en": "Served from the catalogue.",
        "ja": "カタログから提供しました。",
    },
    "job.catalogoptions": {
        "en": "{n} options served from the catalogue. Pick one.",
        "ja": "カタログから {n} 案を提供しました。どれか選んでください。",
    },

    # -- the catalogue path -------------------------------------------------
    "catalog.served": {
        "en": "{title} - served from the catalogue, not generated",
        "ja": "{title} — 生成ではなくカタログから提供されました",
    },
    "catalog.options": {
        "en": "This request has more than one right answer, so here are {n} "
              "of them, built and checked. Pick the one you meant - it is "
              "finished, not a preview.",
        "ja": "この依頼には正解が複数あるため、構築と検証を済ませた {n} 案を"
              "示します。意図に合うものを選んでください。プレビューではなく"
              "完成した部品です。",
    },
    "catalog.built": {
        "en": "Built in {ms} ms with no model call. Edit it like any other "
              "part - it is parametric source.",
        "ja": "モデルを呼び出さずに {ms} ミリ秒で構築しました。パラメトリック"
              "なソースなので、他の部品と同じように編集できます。",
    },

    # -- edits --------------------------------------------------------------
    "edit.nocontext": {
        "en": "That run cannot be edited in this session.",
        "ja": "この実行は、現在のセッションでは編集できません。",
    },
    "edit.needsrefiner": {
        "en": "That is not a parameter change ({reason}), so it needs the "
              "Refiner agent - but no model backend is available: {problem} "
              "Try naming a dimension the script declares.",
        "ja": "これはパラメータの変更ではなく（{reason}）、リファイナー"
              "エージェントが必要ですが、モデルのバックエンドが利用でき"
              "ません: {problem} スクリプトが宣言している寸法名を指定して"
              "みてください。",
    },
    "edit.askingrefiner": {
        "en": "Not a parameter change ({reason}) - asking the Refiner agent.",
        "ja": "パラメータの変更ではありません（{reason}）。リファイナー"
              "エージェントに依頼します。",
    },
    "edit.unbuildable": {
        "en": "That change could not be built: {error_type}. The previous "
              "version is unchanged.",
        "ja": "この変更は構築できませんでした: {error_type}。直前の"
              "バージョンは変更されていません。",
    },
    "edit.failed": {
        "en": "The edit failed: {error}",
        "ja": "編集に失敗しました: {error}",
    },
    "edit.queued": {
        "en": "Edit queued.",
        "ja": "変更を受け付けました。",
    },
    "edit.applied": {
        "en": "Edit applied.",
        "ja": "変更を適用しました。",
    },

    # -- refused requests ---------------------------------------------------
    "http.needprompt": {
        "en": "A prompt is required.",
        "ja": "プロンプトを入力してください。",
    },
    "http.promptlong": {
        "en": "Prompt is too long.",
        "ja": "プロンプトが長すぎます。",
    },
    "http.nocadquery": {
        "en": "CadQuery is not available in this environment: {detail}",
        "ja": "この環境では CadQuery を利用できません: {detail}",
    },
    "http.nojob": {
        "en": "No such job.",
        "ja": "該当するジョブがありません。",
    },
    "http.nothingtoedit": {
        "en": "That run produced nothing to edit.",
        "ja": "この実行には編集できる結果がありません。",
    },
    "http.stillworking": {
        "en": "That run is still working; wait for it to finish.",
        "ja": "この実行はまだ処理中です。完了までお待ちください。",
    },
    "http.needinstruction": {
        "en": "An instruction is required.",
        "ja": "変更内容を入力してください。",
    },
    "http.instructionlong": {
        "en": "Instruction is too long.",
        "ja": "変更内容が長すぎます。",
    },
    # The parameter panel posts names and numbers rather than a sentence, so
    # it is refused on the same terms: by name, and before anything is queued.
    "http.needchanges": {
        "en": "No parameter changes were given.",
        "ja": "変更するパラメータが指定されていません。",
    },
    "http.noparameter": {
        "en": "This script has no parameter called {name}.",
        "ja": "このスクリプトに {name} というパラメータはありません。",
    },
    "http.badvalue": {
        "en": "{name} needs a number, not {value!r}.",
        "ja": "{name} には数値が必要です（{value!r} は使えません）。",
    },
    "http.notpositive": {
        "en": "{name} must be greater than zero.",
        "ja": "{name} は 0 より大きい値にしてください。",
    },
    "http.nochange": {
        "en": "Every value given is the one the script already has.",
        "ja": "指定された値はすべて現在の値と同じです。",
    },
    "http.norebuild": {
        "en": "CadQuery is not available, so nothing can be rebuilt.",
        "ja": "CadQuery が利用できないため、再構築できません。",
    },
    "http.badversion": {
        "en": "Invalid version.",
        "ja": "バージョンの指定が不正です。",
    },
    "http.noversion": {
        "en": "No such version.",
        "ja": "該当するバージョンがありません。",
    },
    "http.noreplay": {
        "en": "That run has no recorded events or geometry to replay.",
        "ja": "この実行には、再生できるイベントや形状が記録されていません。",
    },
    "http.noprovider": {
        "en": "Unknown provider.",
        "ja": "不明なプロバイダーです。",
    },
    "http.valuelong": {
        "en": "Value is too long.",
        "ja": "入力値が長すぎます。",
    },
    "http.noartifact": {
        "en": "Unknown artifact.",
        "ja": "不明なアーティファクトです。",
    },
    "http.artifactmissing": {
        "en": "Artifact not available.",
        "ja": "アーティファクトが見つかりません。",
    },
    "http.nodrawing": {
        "en": "Could not build the drawing: {error}",
        "ja": "図面を作成できませんでした: {error}",
    },
    "http.jsonbody": {
        "en": "Expected a JSON body.",
        "ja": "JSON 形式の本文が必要です。",
    },
    "http.jsonobject": {
        "en": "Expected a JSON object.",
        "ja": "JSON オブジェクトが必要です。",
    },
    "http.nofrontend": {
        "en": "Frontend is not built.",
        "ja": "フロントエンドがビルドされていません。",
    },
}


def normalise(lang: Optional[str]) -> str:
    """The nearest language this app has, for anything a client sends.

    Accepts a bare tag or a region-qualified one - ``ja``, ``ja-JP``, ``JA``
    all mean Japanese - and falls back to English rather than refusing.
    """
    if not lang:
        return DEFAULT_LANG
    code = str(lang).strip().lower().replace("_", "-").split("-")[0]
    return code if code in LANGS else DEFAULT_LANG


def from_header(accept_language: Optional[str]) -> str:
    """The first language in an ``Accept-Language`` header that we speak.

    Quality values are honoured only in the order they arrive, which is what
    browsers send anyway; a full q-sort would be precision this does not need.
    """
    if not accept_language:
        return DEFAULT_LANG
    for part in str(accept_language).split(","):
        tag = part.split(";")[0].strip()
        code = normalise(tag)
        if code != DEFAULT_LANG or tag.lower().startswith("en"):
            return code
    return DEFAULT_LANG


def has(key: str) -> bool:
    """Whether there is a message under this key.

    For callers that build a key from data - a process name, a material -
    and need to tell "no translation for this one" from a translation that
    happens to read like its key.
    """
    return key in MESSAGES


def t(key: str, lang: Optional[str] = None, **params) -> str:
    """One message, in ``lang``, with its placeholders filled in.

    An unknown key returns the key itself rather than raising: a message that
    reads oddly is a smaller failure than a run that stops.
    """
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    code = normalise(lang)
    text = entry.get(code) or entry[DEFAULT_LANG]
    if not params:
        return text
    try:
        return text.format(**params)
    except (KeyError, IndexError):
        # A placeholder the caller did not supply: show the message rather
        # than losing it to a formatting error.
        return text


def check() -> list[str]:
    """Keys that are missing a translation, for the test suite to fail on."""
    missing = []
    for key, entry in MESSAGES.items():
        for lang in LANGS:
            if not entry.get(lang):
                missing.append(f"{key}:{lang}")
    return missing

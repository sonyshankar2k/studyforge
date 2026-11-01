"""Eligibility criteria, Schedule of Activities and the USDM export."""

import pytest

from app.seed import seed_demo_data


async def add_criterion(client, study_id, text, category="inclusion"):
    resp = await client.post(
        f"/api/studies/{study_id}/criteria", json={"category": category, "text": text}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def criteria(client, study_id):
    return (await client.get(f"/api/studies/{study_id}/criteria")).json()


# ------------------------------------------------------------------ criteria


async def test_criteria_are_numbered_per_category(client, study):
    sid = study["id"]
    await add_criterion(client, sid, "Adults aged 18 to 65")
    await add_criterion(client, sid, "Current smoker", "exclusion")
    await add_criterion(client, sid, "Diagnosed asthma")

    items = await criteria(client, sid)
    assert [(c["identifier"], c["text"]) for c in items] == [
        ("I1", "Adults aged 18 to 65"),
        ("I2", "Diagnosed asthma"),
        ("E1", "Current smoker"),
    ]


async def test_deleting_a_criterion_renumbers_the_rest(client, study):
    sid = study["id"]
    first = await add_criterion(client, sid, "First inclusion")
    await add_criterion(client, sid, "Second inclusion")
    await add_criterion(client, sid, "Third inclusion")

    resp = await client.delete(f"/api/criteria/{first['id']}?version=1")
    assert resp.status_code == 204
    items = await criteria(client, sid)
    assert [(c["identifier"], c["text"]) for c in items] == [
        ("I1", "Second inclusion"),
        ("I2", "Third inclusion"),
    ]


async def test_reorder_criteria(client, study):
    sid = study["id"]
    a = await add_criterion(client, sid, "Criterion A")
    b = await add_criterion(client, sid, "Criterion B")
    c = await add_criterion(client, sid, "Criterion C")

    resp = await client.put(
        f"/api/studies/{sid}/criteria/order",
        json={"category": "inclusion", "ids": [c["id"], a["id"], b["id"]]},
    )
    assert resp.status_code == 200
    assert [(x["identifier"], x["text"]) for x in resp.json()] == [
        ("I1", "Criterion C"),
        ("I2", "Criterion A"),
        ("I3", "Criterion B"),
    ]
    audit = (await client.get(f"/api/studies/{sid}/audit")).json()
    assert audit[0]["action"] == "reorder"


async def test_reorder_with_a_stale_list_is_rejected(client, study):
    sid = study["id"]
    a = await add_criterion(client, sid, "Criterion A")
    b = await add_criterion(client, sid, "Criterion B")
    await add_criterion(client, sid, "Added by someone else meanwhile")

    resp = await client.put(
        f"/api/studies/{sid}/criteria/order",
        json={"category": "inclusion", "ids": [b["id"], a["id"]]},
    )
    assert resp.status_code == 409


async def test_reorder_rejects_duplicate_ids(client, study):
    sid = study["id"]
    a = await add_criterion(client, sid, "Criterion A")
    resp = await client.put(
        f"/api/studies/{sid}/criteria/order",
        json={"category": "inclusion", "ids": [a["id"], a["id"]]},
    )
    assert resp.status_code == 409


async def test_edit_criterion_uses_optimistic_concurrency(client, study, auth):
    sid = study["id"]
    crit = await add_criterion(client, sid, "Adults aged 18 to 65")
    ok = await client.patch(
        f"/api/criteria/{crit['id']}", json={"version": 1, "text": "Adults aged 18 to 75"}
    )
    assert ok.json()["version"] == 2
    stale = await client.patch(
        f"/api/criteria/{crit['id']}",
        json={"version": 1, "text": "Adults aged 21 to 65"},
        headers=auth["bob"],
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["current"]["text"] == "Adults aged 18 to 75"


async def test_criterion_text_must_be_meaningful(client, study):
    resp = await client.post(
        f"/api/studies/{study['id']}/criteria", json={"category": "inclusion", "text": "x"}
    )
    assert resp.status_code == 422


# ------------------------------------------------------------------ schedule


@pytest.fixture
async def grid(client, study):
    """Two visits x two activities."""
    sid = study["id"]
    screening = (
        await client.post(f"/api/studies/{sid}/encounters", json={"name": "Screening", "day": -14})
    ).json()
    day1 = (
        await client.post(
            f"/api/studies/{sid}/encounters",
            json={"name": "Day 1", "day": 1, "window_before": 0, "window_after": 2},
        )
    ).json()
    vitals = (await client.post(f"/api/studies/{sid}/activities", json={"name": "Vitals"})).json()
    labs = (await client.post(f"/api/studies/{sid}/activities", json={"name": "Labs"})).json()
    return {"sid": sid, "screening": screening, "day1": day1, "vitals": vitals, "labs": labs}


async def set_cell(client, sid, encounter, activity, planned=True):
    return await client.put(
        f"/api/studies/{sid}/schedule/cells",
        json={"encounter_id": encounter["id"], "activity_id": activity["id"], "planned": planned},
    )


async def test_schedule_lists_visits_by_day_and_activities_in_order(client, grid):
    # Add a visit out of order: it must still sort by study day.
    await client.post(f"/api/studies/{grid['sid']}/encounters", json={"name": "Week 4", "day": 29})
    sched = (await client.get(f"/api/studies/{grid['sid']}/schedule")).json()
    assert [e["name"] for e in sched["encounters"]] == ["Screening", "Day 1", "Week 4"]
    assert [(a["name"], a["ordinal"]) for a in sched["activities"]] == [("Vitals", 1), ("Labs", 2)]
    assert sched["cells"] == []


async def test_planning_a_cell_is_idempotent(client, grid):
    first = await set_cell(client, grid["sid"], grid["day1"], grid["vitals"])
    again = await set_cell(client, grid["sid"], grid["day1"], grid["vitals"])
    assert first.json()["changed"] is True
    assert again.json()["changed"] is False  # same request twice: no harm, no duplicate

    sched = (await client.get(f"/api/studies/{grid['sid']}/schedule")).json()
    assert sched["cells"] == [
        {"encounter_id": grid["day1"]["id"], "activity_id": grid["vitals"]["id"]}
    ]

    off = await set_cell(client, grid["sid"], grid["day1"], grid["vitals"], planned=False)
    assert off.json()["changed"] is True
    assert (await client.get(f"/api/studies/{grid['sid']}/schedule")).json()["cells"] == []


async def test_cells_are_audited_in_plain_words(client, grid):
    await set_cell(client, grid["sid"], grid["screening"], grid["labs"])
    latest = (await client.get(f"/api/studies/{grid['sid']}/audit")).json()[0]
    assert latest["entity_type"] == "schedule"
    assert latest["changes"] == {"Labs @ Screening": {"old": "not planned", "new": "planned"}}


async def test_cells_must_belong_to_the_study(client, grid):
    other = (await client.post("/api/studies", json={"title": "Another study"})).json()
    resp = await set_cell(client, other["id"], grid["day1"], grid["vitals"])
    assert resp.status_code == 422
    missing = await client.put(
        f"/api/studies/{grid['sid']}/schedule/cells",
        json={"encounter_id": 999, "activity_id": grid["vitals"]["id"], "planned": True},
    )
    assert missing.status_code == 404


async def test_deleting_a_visit_removes_its_cells(client, grid):
    await set_cell(client, grid["sid"], grid["day1"], grid["vitals"])
    await set_cell(client, grid["sid"], grid["screening"], grid["vitals"])
    resp = await client.delete(f"/api/encounters/{grid['day1']['id']}?version=1")
    assert resp.status_code == 204
    sched = (await client.get(f"/api/studies/{grid['sid']}/schedule")).json()
    assert [c["encounter_id"] for c in sched["cells"]] == [grid["screening"]["id"]]
    audit = (await client.get(f"/api/studies/{grid['sid']}/audit")).json()[0]
    assert audit["changes"]["planned_activities_removed"] == 1


async def test_deleting_an_activity_removes_its_cells(client, grid):
    await set_cell(client, grid["sid"], grid["day1"], grid["labs"])
    assert (
        await client.delete(f"/api/activities/{grid['labs']['id']}?version=1")
    ).status_code == 204
    assert (await client.get(f"/api/studies/{grid['sid']}/schedule")).json()["cells"] == []


async def test_visit_and_activity_names_are_unique_per_study(client, grid):
    dup_visit = await client.post(
        f"/api/studies/{grid['sid']}/encounters", json={"name": " screening ", "day": 3}
    )
    dup_activity = await client.post(
        f"/api/studies/{grid['sid']}/activities", json={"name": "VITALS"}
    )
    assert dup_visit.status_code == 422
    assert dup_activity.status_code == 422


async def test_names_that_only_differ_in_non_ascii_case_never_cause_a_500(client, grid):
    # SQLite's lower() ignores non-ASCII letters, so the friendly pre-check can miss
    # this duplicate; the database constraint must still turn it into a clean 422.
    url = f"/api/studies/{grid['sid']}/encounters"
    assert (await client.post(url, json={"name": "Ärztliche Visite", "day": 7})).status_code == 201
    again = await client.post(url, json={"name": "Ärztliche Visite", "day": 8})
    assert again.status_code == 422
    assert again.json()["detail"][0]["loc"] == ["body", "name"]


async def test_visit_window_and_day_limits(client, study):
    resp = await client.post(
        f"/api/studies/{study['id']}/encounters",
        json={"name": "Bad", "day": 1, "window_before": -1},
    )
    assert resp.status_code == 422


async def test_rename_visit_uses_optimistic_concurrency(client, grid):
    url = f"/api/encounters/{grid['day1']['id']}"
    assert (await client.patch(url, json={"version": 1, "name": "Baseline"})).status_code == 200
    assert (await client.patch(url, json={"version": 1, "name": "Day One"})).status_code == 409


# ------------------------------------------------------------------ USDM export


async def test_usdm_export_contains_the_whole_design(client, grid):
    sid = grid["sid"]
    await client.post(
        f"/api/studies/{sid}/arms",
        json={"name": "Drug 10 mg", "arm_type": "experimental", "dose": "10 mg daily"},
    )
    await client.post(
        f"/api/studies/{sid}/objectives",
        json={"level": "primary", "description": "Efficacy", "endpoint": "FEV1 at Week 12"},
    )
    await add_criterion(client, sid, "Adults aged 18 to 65")
    await set_cell(client, sid, grid["day1"], grid["vitals"])

    usdm = (await client.get(f"/api/studies/{sid}/usdm")).json()
    design = usdm["study"]["versions"][0]["studyDesigns"][0]

    assert design["instanceType"] == "StudyDesign"
    assert design["arms"][0]["type"]["decode"] == "Experimental Arm"
    assert "Dose: 10 mg daily" in design["arms"][0]["description"]
    assert design["objectives"][0]["endpoints"][0]["text"] == "FEV1 at Week 12"
    assert design["eligibilityCriteria"][0]["identifier"] == "I1"
    assert [e["name"] for e in design["encounters"]] == ["Screening", "Day 1"]
    instances = design["scheduleTimelines"][0]["instances"]
    day1 = next(i for i in instances if i["encounterId"] == f"Encounter_{grid['day1']['id']}")
    assert day1["activityIds"] == [f"Activity_{grid['vitals']['id']}"]


async def test_design_endpoints_require_sign_in(anon_client):
    for url in ("/api/studies/1/criteria", "/api/studies/1/schedule", "/api/studies/1/usdm"):
        assert (await anon_client.get(url)).status_code == 401


# ------------------------------------------------------------------ demo data


async def test_demo_design_is_seeded_once_and_never_re_added(session_factory, client):
    async with session_factory() as session:
        await seed_demo_data(session)
    studies = (await client.get("/api/studies")).json()
    demo = next(s for s in studies if s["acronym"] == "BREATHE-1")
    sched = (await client.get(f"/api/studies/{demo['id']}/schedule")).json()
    assert len(sched["encounters"]) == 6 and len(sched["activities"]) == 7

    # A user deletes a visit; restarting the app must not bring it back.
    screening = sched["encounters"][0]
    await client.delete(f"/api/encounters/{screening['id']}?version=1")
    async with session_factory() as session:
        await seed_demo_data(session)
    sched = (await client.get(f"/api/studies/{demo['id']}/schedule")).json()
    assert len(sched["encounters"]) == 5

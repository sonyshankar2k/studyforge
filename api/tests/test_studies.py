"""API tests: CRUD, optimistic concurrency, conditional validation, audit trail."""


async def test_health(anon_client):
    client = anon_client
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_create_and_get_study(client, study):
    resp = await client.get(f"/api/studies/{study['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Test Study"
    assert body["version"] == 1
    assert body["status"] == "draft"
    assert body["arms"] == []


async def test_study_title_too_short_is_rejected(client):
    resp = await client.post("/api/studies", json={"title": "ab"})
    assert resp.status_code == 422


async def test_update_increments_version(client, study):
    resp = await client.patch(f"/api/studies/{study['id']}", json={"version": 1, "acronym": "TS-1"})
    assert resp.status_code == 200
    assert resp.json()["acronym"] == "TS-1"
    assert resp.json()["version"] == 2


async def test_stale_update_returns_409_with_current_record(client, study, auth):
    sid = study["id"]
    # Alice saves first (version 1 -> 2)
    first = await client.patch(
        f"/api/studies/{sid}",
        json={"version": 1, "title": "Alice's title"},
        headers=auth["alice"],
    )
    assert first.status_code == 200

    # Bob still holds version 1, so his save must be rejected
    second = await client.patch(
        f"/api/studies/{sid}",
        json={"version": 1, "title": "Bob's title"},
        headers=auth["bob"],
    )
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["current"]["title"] == "Alice's title"
    assert detail["current"]["version"] == 2


async def test_no_op_update_does_not_bump_version(client, study):
    resp = await client.patch(
        f"/api/studies/{study['id']}", json={"version": 1, "title": "Test Study"}
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 1


async def test_experimental_arm_requires_dose(client, study):
    resp = await client.post(
        f"/api/studies/{study['id']}/arms",
        json={"name": "Drug A", "arm_type": "experimental"},
    )
    assert resp.status_code == 422


async def test_placebo_arm_without_dose_is_ok(client, study):
    resp = await client.post(
        f"/api/studies/{study['id']}/arms",
        json={"name": "Placebo", "arm_type": "placebo", "planned_size": 50},
    )
    assert resp.status_code == 201
    assert resp.json()["version"] == 1


async def test_switching_arm_to_experimental_without_dose_is_rejected(client, study):
    created = await client.post(
        f"/api/studies/{study['id']}/arms", json={"name": "Arm B", "arm_type": "placebo"}
    )
    arm = created.json()
    resp = await client.patch(
        f"/api/arms/{arm['id']}", json={"version": 1, "arm_type": "experimental"}
    )
    assert resp.status_code == 422


async def test_delete_arm_with_stale_version_is_rejected(client, study):
    created = await client.post(
        f"/api/studies/{study['id']}/arms", json={"name": "Arm C", "arm_type": "placebo"}
    )
    arm = created.json()
    await client.patch(f"/api/arms/{arm['id']}", json={"version": 1, "name": "Arm C2"})

    stale = await client.delete(f"/api/arms/{arm['id']}?version=1")
    assert stale.status_code == 409

    ok = await client.delete(f"/api/arms/{arm['id']}?version=2")
    assert ok.status_code == 204


async def test_audit_trail_records_who_changed_what(client, study, auth):
    sid = study["id"]
    await client.patch(
        f"/api/studies/{sid}",
        json={"version": 1, "title": "New Title"},
        headers=auth["carol"],
    )
    resp = await client.get(f"/api/studies/{sid}/audit")
    entries = resp.json()

    assert len(entries) == 2  # create + update, newest first
    latest = entries[0]
    assert latest["action"] == "update"
    assert latest["changed_by"] == "carol@test.dev"
    assert latest["changes"]["title"] == {"old": "Test Study", "new": "New Title"}
    assert entries[1]["action"] == "create"
    assert entries[1]["changed_by"] == "alice@test.dev"


async def test_objective_crud(client, study):
    sid = study["id"]
    created = await client.post(
        f"/api/studies/{sid}/objectives",
        json={"level": "primary", "description": "Efficacy", "endpoint": "FEV1 at Week 12"},
    )
    assert created.status_code == 201
    obj = created.json()

    updated = await client.patch(
        f"/api/objectives/{obj['id']}", json={"version": 1, "endpoint": "FEV1 at Week 24"}
    )
    assert updated.json()["endpoint"] == "FEV1 at Week 24"

    deleted = await client.delete(f"/api/objectives/{obj['id']}?version=2")
    assert deleted.status_code == 204

    detail = await client.get(f"/api/studies/{sid}")
    assert detail.json()["objectives"] == []


async def test_acronym_availability_check(client):
    await client.post("/api/studies", json={"title": "Study One", "acronym": "ONE"})

    taken = await client.get("/api/studies/acronym-available", params={"acronym": "one"})
    assert taken.json() == {"available": False}

    free = await client.get("/api/studies/acronym-available", params={"acronym": "TWO"})
    assert free.json() == {"available": True}

    duplicate = await client.post("/api/studies", json={"title": "Study Two", "acronym": "ONE"})
    assert duplicate.status_code == 422

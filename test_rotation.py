import json

MAX_PLAYERS = 5

state = {
    "active": [
        {"user": "@P1", "name": "@P1"},
        {"user": "@P2", "name": "@P2"},
        {"user": "@P3", "name": "@P3"},
        {"user": "@P4", "name": "@P4"},
        {"user": "@P5", "name": "@P5"},
    ],
    "queue": [
        {"user": "@Q1", "name": "@Q1"},
        {"user": "@Q2", "name": "@Q2"},
    ]
}

print("SEBELUM:")
print("ACTIVE :", [p["name"] for p in state["active"]])
print("QUEUE  :", [p["name"] for p in state["queue"]])

# P5 keluar
eliminated = state["active"].pop(4)

# Queue pertama masuk
if state["queue"] and len(state["active"]) < MAX_PLAYERS:
    incoming = state["queue"].pop(0)
    state["active"].append(incoming)
else:
    incoming = None

print("\nHASIL ROTASI:")
print("KELUAR :", eliminated["name"])
print("MASUK  :", incoming["name"] if incoming else "-")
print("ACTIVE :", [p["name"] for p in state["active"]])
print("QUEUE  :", [p["name"] for p in state["queue"]])

assert [p["name"] for p in state["active"]] == [
    "@P1", "@P2", "@P3", "@P4", "@Q1"
]

assert [p["name"] for p in state["queue"]] == ["@Q2"]

print("\nROTASI TEST: BERHASIL")

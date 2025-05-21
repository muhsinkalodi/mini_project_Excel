import json

with open("student-performance-app-3e7d7-firebase-adminsdk-fbsvc-ab6415d037.json") as f:
    data = json.load(f)

print(json.dumps(data))

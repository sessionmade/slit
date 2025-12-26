from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1452087020406050990/fYbESu7ZnBs47iPuFQ9vbSf60L1zYUcwwPCJRJsycA62bTW57jQlWM0R5oThoYW1xlu-"

GITHUB_AVATAR = "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png"

def send_discord_embed(embed: dict):
    payload = {
        "username": "GitHub",
        "avatar_url": GITHUB_AVATAR,
        "embeds": [embed]
    }
    requests.post(DISCORD_WEBHOOK, json=payload)


@app.route("/github", methods=["POST"])
def github_webhook():
    event = request.headers.get("X-GitHub-Event")
    data = request.json

    # ───────────── PUSH ─────────────
    if event == "push":
        commit = data["head_commit"]

        embed = {
            "title": "🚀 New Commit Pushed",
            "url": commit["url"],
            "color": 0x2F81F7,
            "author": {
                "name": data["repository"]["full_name"],
                "url": data["repository"]["html_url"]
            },
            "description": commit["message"],
            "fields": [
                {
                    "name": "Author",
                    "value": commit["author"]["name"],
                    "inline": True
                },
                {
                    "name": "Branch",
                    "value": data["ref"].replace("refs/heads/", ""),
                    "inline": True
                }
            ],
            "timestamp": commit["timestamp"]
        }

        send_discord_embed(embed)

    # ───────────── RELEASE ─────────────
    elif event == "release":
        release = data["release"]

        embed = {
            "title": f"🏷️ New Release: {release['tag_name']}",
            "url": release["html_url"],
            "color": 0x3FB950,
            "description": release["body"] or "No release notes provided.",
            "fields": [
                {
                    "name": "Author",
                    "value": release["author"]["login"],
                    "inline": True
                },
                {
                    "name": "Pre-release",
                    "value": str(release["prerelease"]),
                    "inline": True
                }
            ],
            "timestamp": release["published_at"]
        }

        send_discord_embed(embed)

    return jsonify({"status": "ok"}), 200

def start():
    app.run(host="0.0.0.0", port=6969)

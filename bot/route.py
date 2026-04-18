from aiohttp import web
import json
from .config import config
from .database.database import db
from .utils.media_manager import get_photo_url

async def cors_middleware(app, handler):
    async def middleware(request):
        if request.method == "OPTIONS":
            response = web.Response(status=204)
        else:
            response = await handler(request)
        
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response
    return middleware

routes = web.RouteTableDef()

@routes.get("/robots.txt")
async def robots(request):
    return web.Response(text="User-agent: *\nDisallow: /api/\nAllow: /")

@routes.get("/", allow_head=True)
async def index(request):
    return web.json_response({"status": "running", "application": config.application.name})

@routes.get("/api/categories")
async def get_categories(request):
    # Unique categories with channel + subscriber counts
    categories_raw = await db.channels.distinct("category", {"is_active": True, "is_banned": {"$ne": True}, "category": {"$ne": None}})
    categories_data = []
    for cat in sorted(categories_raw):
        ch_count = await db.channels.count_documents({"is_active": True, "is_banned": {"$ne": True}, "category": cat})
        # Sum members for subscriber total
        pipeline = [
            {"$match": {"is_active": True, "is_banned": {"$ne": True}, "category": cat}},
            {"$group": {"_id": None, "total_members": {"$sum": "$members_count"}}}
        ]
        agg = db.channels.aggregate(pipeline)
        total_members = 0
        async for doc in agg:
            total_members = doc.get("total_members", 0)

        categories_data.append({
            "name": cat,
            "channels_count": ch_count,
            "total_members": total_members
        })

    return web.json_response({"categories": categories_data})

@routes.get("/api/channels")
async def get_channels(request):
    query = request.query
    search_query = query.get("q", "").strip()
    category = query.get("cat", None)
    sort_by = query.get("sort", "members_count")
    limit = int(query.get("limit", 50))
    offset = int(query.get("offset", 0))

    mongo_query = {"is_active": True, "is_banned": {"$ne": True}}

    if search_query:
        mongo_query["title"] = {"$regex": search_query, "$options": "i"}

    if category and category not in ("all", "channels", "groups", "stickers", "bots"):
        mongo_query["category"] = {"$regex": f"^{category}$", "$options": "i"}

    # --- Sponsor channels (paid_promos) pinned at the top ---
    sponsor_items = []
    # Only show sponsors on the first page (offset 0) and not during search
    if offset == 0 and not search_query:
        sponsor_query = {"is_active": True}
        if category and category not in ("all", "channels", "groups", "stickers", "bots"):
            # Only show sponsors for this category OR global sponsors (empty list)
            sponsor_query["$or"] = [
                {"categories": category},
                {"categories": {"$size": 0}},
                {"categories": {"$exists": False}},
                {"categories": None}
            ]
            
        sponsor_cursor = db.paid_promos.find(sponsor_query)
        async for promo in sponsor_cursor:
            # Try to resolve a photo by matching the promo URL to a known channel username
            promo_url = promo.get("url", "")
            promo_username = None
            if "t.me/" in promo_url:
                # Extract username from https://t.me/username or https://t.me/+hash
                parts = promo_url.rstrip("/").split("t.me/")
                if len(parts) > 1 and not parts[1].startswith("+"):
                    promo_username = parts[1].split("/")[0].lstrip("@")

            resolved_photo = get_photo_url(promo.get("photo", ""))
            resolved_members = promo.get("members_count", 0)

            # Fallback to channel lookup if photo is missing
            if not resolved_photo and promo_username:
                ch_doc = await db.channels.find_one(
                    {"username": {"$regex": f"^{promo_username}$", "$options": "i"}},
                    {"photo": 1, "members_count": 1}
                )
                if ch_doc:
                    resolved_photo = get_photo_url(ch_doc.get("photo", ""))
                    resolved_members = ch_doc.get("members_count", 0)

            sponsor_items.append({
                "channel_id": promo.get("promo_id"),
                "title": promo.get("name") or promo.get("text", "Sponsor"),
                "username": promo_username,
                "link": promo_url,
                "members_count": resolved_members,
                "members_formatted": _format_number(resolved_members) if resolved_members else "",
                "category": (promo.get("categories") or [""])[0],
                "language": (promo.get("languages") or ["fr"])[0],
                "about": promo.get("text", ""),
                "photo": resolved_photo,
                "ratio": 0.0,
                "added_date": str(promo.get("added_date", "")),
                "is_sponsored": True,
            })

    # --- Regular channels ---
    # Fetch total count to inform frontend about has_more
    total_count = await db.channels.count_documents(mongo_query)
    
    cursor = db.channels.find(mongo_query).sort(sort_by, -1).skip(offset).limit(limit)
    channels = []
    async for ch in cursor:
        members = ch.get("members_count", 0)
        channels.append({
            "channel_id": ch.get("channel_id"),
            "title": ch.get("title"),
            "username": ch.get("username"),
            "link": ch.get("link"),
            "members_count": members,
            "members_formatted": _format_number(members),
            "category": ch.get("category"),
            "language": ch.get("language", "fr"),
            "about": ch.get("about", ""),
            "photo": get_photo_url(ch.get("photo")),
            "ratio": ch.get("ratio", 0.0),
            "added_date": str(ch.get("added_date", "")),
            "is_sponsored": False,
        })

    all_channels = sponsor_items + channels
    has_more = (offset + limit) < total_count
    
    return web.json_response({
        "channels": all_channels, 
        "total": total_count,
        "has_more": has_more,
        "offset": offset,
        "limit": limit
    })

@routes.get("/api/stats")
async def get_stats(request):
    """Returns real global stats for the Hub home page."""
    total_channels = await db.channels.count_documents({"is_active": True, "is_banned": {"$ne": True}})
    total_users = await db.users.count_documents({})
    total_ads = await db.adscross.count_documents({})
    total_posts = await db.posts.count_documents({})
    total_bots = await db.db["clones"].count_documents({"is_active": True})

    # Total members across all active channels
    pipeline = [
        {"$match": {"is_active": True, "is_banned": {"$ne": True}}},
        {"$group": {"_id": None, "total_members": {"$sum": "$members_count"}}}
    ]
    total_members = 0
    async for doc in db.channels.aggregate(pipeline):
        total_members = doc.get("total_members", 0)

    return web.json_response({
        "total_channels": total_channels,
        "total_channels_formatted": _format_number(total_channels),
        "total_users": total_users,
        "total_users_formatted": _format_number(total_users),
        "total_ads": total_ads,
        "total_posts": total_posts,
        "total_bots": total_bots,
        "total_members": total_members,
        "total_members_formatted": _format_number(total_members),
    })

def _format_number(n: int) -> str:
    """Format large numbers to human-readable format (e.g. 1.3M, 450k)."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)

async def web_server():
    web_app = web.Application(middlewares=[cors_middleware], client_max_size=1024*1024*1024)
    web_app.add_routes(routes)
    return web_app
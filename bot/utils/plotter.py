import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import io
import pendulum

def generate_growth_chart(history_data: list, timeframe_days: int = 7, lang: str = "fr") -> io.BytesIO:
    """
    Generates a stylized matplotlib chart.
    history_data: list of dicts: {"date": "YYYY-MM-DD", "total": int, "bot_joins": int}
    """
    sns.set_theme(style="darkgrid", context="talk")
    
    # Sort history just in case
    history = sorted(history_data, key=lambda x: x["date"])
    
    if not history:
        # Dummy data if none
        now = pendulum.now()
        history = [
            {"date": now.subtract(days=1).format("YYYY-MM-DD"), "total": 0, "bot_joins": 0},
            {"date": now.format("YYYY-MM-DD"), "total": 0, "bot_joins": 0}
        ]
        
    if timeframe_days > 0:
        cutoff = pendulum.now().subtract(days=timeframe_days).format("YYYY-MM-DD")
        history = [h for h in history if h["date"] >= cutoff]
        
    dates = [h["date"][-5:] for h in history]  # Only MM-DD for readability
    totals = [h["total"] for h in history]
    bot_joins = [h.get("bot_joins", 0) for h in history]
    
    fig, ax = plt.subplots(figsize=(10, 5))
    
    # Main line for Total Members
    label_total = "Total Members" if lang == "en" else "Membres Totaux"
    ax.plot(dates, totals, marker='o', color='#1d9bf0', linewidth=2.5, label=label_total)
    
    # Fill under curve
    ax.fill_between(dates, totals, alpha=0.1, color='#1d9bf0')
    
    # Optional bar for bot joins (if scale matches)
    if any(bot_joins):
        label_bot = "Joined via Bot" if lang == "en" else "Rejoints via Bot"
        ax.bar(dates, bot_joins, alpha=0.5, color='#00ba7c', label=label_bot, width=0.4)
        
    title = f"Growth Dynamics ({timeframe_days} Days)" if lang == "en" else f"Dynamique de Croissance ({timeframe_days} Jours)"
    if timeframe_days == 0:
        title = "All-Time Growth Dynamics" if lang == "en" else "Croissance Quotidienne (Tout le temps)"
        
    ax.set_title(title, pad=20, fontsize=16, fontweight='bold', color="#333333")
    ax.set_xlabel("Date" if lang == "en" else "Date", fontsize=12) # Date is same in both usually, but good practice
    ax.set_ylabel("Members" if lang == "en" else "Membres", fontsize=12)
    
    plt.xticks(rotation=45)
    plt.legend(loc="upper left")
    plt.tight_layout()
    
    # Render to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150)
    buf.seek(0)
    plt.close(fig)
    buf.name = "chart.png"
    return buf

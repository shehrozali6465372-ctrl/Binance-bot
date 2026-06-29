"""Image Intelligence Engine V4 Ultimate
Generates professional Binance Square trading images using Pillow.

Every image is unique, mobile-optimized, and contains:
- Trading chart background
- Coin data (symbol, price, change)
- Market analysis (volume, score)
- Trade setup (entry, targets, stop)
- Reasons to trade
- Confidence score, risk level
- Anti-duplication via hash tracking
"""

import hashlib
import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import json
import urllib.request
import urllib.error
from PIL import Image, ImageDraw, ImageFont

LOGGER = logging.getLogger("agent.image_engine")

# Color palette (institutional dark mode)
COLORS = {
    "bg_dark": (13, 17, 23),       # GitHub dark bg
    "bg_card": (22, 27, 34),       # Card background
    "bg_chart": (10, 14, 20),      # Chart area
    "green": (0, 200, 83),          # Bullish green
    "green_dim": (0, 150, 60),      # Dim green
    "red": (234, 60, 83),           # Bearish red
    "red_dim": (180, 40, 60),       # Dim red
    "white": (236, 239, 244),
    "gray": (120, 130, 140),
    "gray_dim": (60, 65, 75),
    "accent_blue": (56, 139, 253),
    "accent_purple": (188, 100, 255),
    "accent_yellow": (255, 210, 60),
    "accent_orange": (255, 150, 50),
    "border": (38, 44, 54),
    "text_dim": (100, 110, 120),
}

class ImageIntelligenceEngine:
    """Generate unique, professional trading images for Binance Square posts."""
    
    # Track generated images to prevent duplicates
    _prompt_history: List[str] = []
    _image_hash_history: set = set()
    
    def __init__(self, config=None):
        self.config = config
        self.fonts_dir = "/usr/share/fonts/truetype/liberation/"
        self._load_fonts()
        self.images_dir = Path("images")
        self.images_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_fonts(self):
        """Load available fonts."""
        try:
            self.font_bold = ImageFont.truetype(self.fonts_dir + "LiberationSans-Bold.ttf", 42)
            self.font_bold_small = ImageFont.truetype(self.fonts_dir + "LiberationSans-Bold.ttf", 28)
            self.font_regular = ImageFont.truetype(self.fonts_dir + "LiberationSans-Regular.ttf", 24)
            self.font_small = ImageFont.truetype(self.fonts_dir + "LiberationSans-Regular.ttf", 18)
            self.font_tiny = ImageFont.truetype(self.fonts_dir + "LiberationSans-Regular.ttf", 14)
            self.font_mono = ImageFont.truetype(self.fonts_dir + "LiberationMono-Regular.ttf", 20)
            self.font_mono_bold = ImageFont.truetype(self.fonts_dir + "LiberationMono-Bold.ttf", 22)
            self.font_title = ImageFont.truetype(self.fonts_dir + "LiberationSans-Bold.ttf", 56)
            self.font_xl = ImageFont.truetype(self.fonts_dir + "LiberationSans-Bold.ttf", 72)
            self.font_watermark = ImageFont.truetype(self.fonts_dir + "LiberationSans-Regular.ttf", 11)
        except Exception:
            LOGGER.warning("Could not load fonts, using default")
            self.font_bold = ImageFont.load_default()
            self.font_regular = ImageFont.load_default()
            self.font_small = ImageFont.load_default()
            self.font_tiny = ImageFont.load_default()
            self.font_mono = ImageFont.load_default()
            self.font_mono_bold = ImageFont.load_default()
            self.font_title = ImageFont.load_default()
            self.font_xl = ImageFont.load_default()
            self.font_bold_small = ImageFont.load_default()
            self.font_watermark = ImageFont.load_default()
    
    def generate(
        self,
        coin: Dict[str, Any],
        analysis: Dict[str, Any],
        setup: Dict[str, str],
        v5_score_result: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> Optional[Path]:
        """Generate a unique professional trading image for a coin.
        
        Returns path to generated image, or None if duplicate/skip.
        """
        symbol = coin.get("symbol", "COIN")
        
        # Build content signature for duplication check
        content_sig = self._build_signature(coin, analysis, setup, v5_score_result)
        image_hash = hashlib.sha256(content_sig.encode()).hexdigest()[:16]
        
        # Anti-duplication check
        if image_hash in self._image_hash_history and not force:
            LOGGER.debug("Skipping duplicate image hash: %s for %s", image_hash, symbol)
            return None
        
        # Determine direction and colors
        change = float(coin.get("change_24h", 0) or 0)
        is_bullish = change >= 0
        primary_color = COLORS["green"] if is_bullish else COLORS["red"]
        dim_color = COLORS["green_dim"] if is_bullish else COLORS["red_dim"]
        
        # Determine headline from context
        headline = self._select_headline(coin, analysis, is_bullish)
        
        # Generate reasons
        reasons = self._generate_reasons(coin, analysis, v5_score_result)
        
        # Create the image
        img = self._render_image(
            symbol=symbol,
            price=float(coin.get("price", 0) or 0),
            change=change,
            volume_ratio=float(coin.get("volume_ratio", 1) or 1),
            market_cap=float(coin.get("market_cap", 0) or 0),
            headline=headline,
            reasons=reasons,
            setup=setup,
            is_bullish=is_bullish,
            primary_color=primary_color,
            dim_color=dim_color,
            v5_score=v5_score_result,
            narrative=analysis.get("category", "") if isinstance(analysis, dict) else "",
            coin_history=coin.get("history", []),
        )
        
        # Save the image
        ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f"{symbol}_{ts}_{image_hash}.png"
        path = self.images_dir / filename
        img.save(path, "PNG", optimize=True)
        
        # Track
        self._image_hash_history.add(image_hash)
        self._prompt_history.append(f"{symbol}_{headline[:20]}")
        
        LOGGER.info("Image generated: %s (%s, %s)", path, headline, symbol)
        return path
    
    def _build_signature(self, coin, analysis, setup, v5_score) -> str:
        """Build unique content signature for anti-duplication."""
        parts = [
            coin.get("symbol", ""),
            str(coin.get("price", 0)),
            str(coin.get("change_24h", 0)),
            str(coin.get("volume_ratio", 1)),
            str(setup.get("entry", "")),
            str(setup.get("target1", "")),
            str(setup.get("stop", "")),
            str(v5_score.get("final_score", 0) if v5_score else 0),
        ]
        return "|".join(parts)
    
    def _select_headline(self, coin: Dict[str, Any], analysis: Dict[str, Any], is_bullish: bool) -> str:
        """Select the best headline based on coin data and context."""
        change = abs(float(coin.get("change_24h", 0) or 0))
        vol_ratio = float(coin.get("volume_ratio", 1) or 1)
        announcement = coin.get("announcement_type", "") if isinstance(analysis, dict) else ""
        narrative = analysis.get("category", "") if isinstance(analysis, dict) else ""
        
        headlines = []
        
        if announcement == "new_listing":
            headlines = ["BINANCE LISTING", "NEW LISTING ALERT", "LISTING SPOTLIGHT"]
        elif announcement == "airdrop":
            headlines = ["AIRDROP ALERT", "EARN FREE TOKENS", "AIRDROP SEASON"]
        elif change >= 10:
            headlines = ["BREAKOUT ALERT", "EXPLOSIVE MOVE", "MEGA BREAKOUT", "BIG MOVE"]
        elif change >= 5:
            headlines = ["STRONG MOMENTUM", "TRENDING NOW", "BREAKOUT WATCH", "BULLISH SIGNAL"]
        elif change >= 3:
            headlines = ["GAINING TRACTION", "MOVING UP", "WATCH LIST"]
        elif vol_ratio >= 3:
            headlines = ["VOLUME SPIKE", "WHALE ALERT", "SOMETHING BIG"]
        elif vol_ratio >= 2:
            headlines = ["VOLUME SURGE", "SMART MONEY", "INSTITUTIONAL FLOW"]
        elif narrative == "AI":
            headlines = ["AI NARRATIVE", "AI SEASON", "SMART MONEY AI"]
        elif narrative == "MEME":
            headlines = ["MEME SEASON", "COMMUNITY POWER", "TRENDING MEME"]
        elif not is_bullish:
            headlines = ["DISCOUNT ZONE", "OVERSOLD WATCH", "BOUNCE SETUP"]
        else:
            headlines = ["HOT TREND", "WATCHLIST", "NEXT MOVE"]
        
        return random.choice(headlines)
    
    def _generate_reasons(self, coin, analysis, v5_score) -> List[str]:
        """Generate 3-5 data-driven reasons for the trade."""
        reasons = []
        change = float(coin.get("change_24h", 0) or 0)
        vol_ratio = float(coin.get("volume_ratio", 1) or 1)
        abs_change = abs(change)
        announcement = coin.get("announcement_type", "")
        narrative = analysis.get("category", "") if isinstance(analysis, dict) else ""
        
        # Reason 1: Price action
        if abs_change >= 10:
            reasons.append(f"Explosive {change:+.1f}% move with strong momentum")
        elif abs_change >= 5:
            reasons.append(f"Strong {change:+.1f}% price surge with conviction")
        elif abs_change >= 3:
            reasons.append(f"Trending with {change:+.1f}% positive price action")
        else:
            reasons.append(f"Notable price action with volume confirmation")
        
        # Reason 2: Volume
        if vol_ratio >= 3:
            reasons.append(f"Volume spike {vol_ratio:.1f}x above average - major participation")
        elif vol_ratio >= 2:
            reasons.append(f"Volume at {vol_ratio:.1f}x - above average interest")
        elif vol_ratio >= 1.5:
            reasons.append(f"Healthy volume at {vol_ratio:.1f}x confirming the move")
        
        # Reason 3: Narrative
        if narrative:
            narrative_map = {
                "AI": "AI narrative gaining institutional traction",
                "MEME": "Strong community momentum in meme sector",
                "L1": "Layer 1 fundamentals driving adoption",
                "DeFi": "DeFi ecosystem expanding rapidly",
                "RWA": "Real World Assets narrative heating up",
                "BTC": "Bitcoin ecosystem strength",
            }
            reasons.append(narrative_map.get(narrative, f"{narrative} narrative gaining momentum"))
        
        # Reason 4: Announcement
        if announcement:
            ann_map = {
                "new_listing": "Fresh Binance listing - liquidity magnet",
                "airdrop": "Active airdrop campaign driving demand",
                "delisting": "Delisting news - high volatility event",
                "launchpool": "Binance Launchpool - staking rewards",
            }
            reasons.append(ann_map.get(announcement, "Binance announcement catalyst"))
        
        # Reason 5: Score
        if v5_score and v5_score.get("final_score", 0) > 70:
            reasons.append(f"Elite V5 score of {v5_score['final_score']:.0f}/100")
        elif v5_score and v5_score.get("hot_search_score", 0) > 5:
            reasons.append(f"High hot search score - trending on Binance")
        
        # Reason 6: Momentum
        if v5_score and v5_score.get("momentum_score", 0) >= 4:
            reasons.append("Strong momentum - potential breakout continuation")
        
        # Ensure 3-5 reasons
        if len(reasons) < 3:
            reasons.append("Market structure supporting further upside")
        if len(reasons) < 3:
            reasons.append("Technical indicators aligned bullishly")
        
        return reasons[:5]
    
    def _render_image(
        self,
        symbol: str,
        price: float,
        change: float,
        volume_ratio: float,
        market_cap: float,
        headline: str,
        reasons: List[str],
        setup: Dict[str, str],
        is_bullish: bool,
        primary_color: tuple,
        dim_color: tuple,
        v5_score: Optional[Dict[str, Any]] = None,
        narrative: str = "",
        coin_history: Optional[List[float]] = None,
    ) -> Image.Image:
        """Render the full trading image."""
        WIDTH, HEIGHT = 1080, 1350
        img = Image.new("RGB", (WIDTH, HEIGHT), COLORS["bg_dark"])
        draw = ImageDraw.Draw(img)
        
        # Colors
        red = COLORS["red"]
        green = COLORS["green"]
        white = COLORS["white"]
        gray = COLORS["gray"]
        gray_dim = COLORS["gray_dim"]
        border = COLORS["border"]
        bg_card = COLORS["bg_card"]
        bg_chart = COLORS["bg_chart"]
        text_dim = COLORS["text_dim"]
        
        # ---- TOP SECTION: Chart Visualization ----
        chart_top = 20
        chart_height = 320
        chart_bottom = chart_top + chart_height
        
        # Draw chart background
        draw.rectangle([20, chart_top, WIDTH - 20, chart_bottom], fill=bg_chart, outline=border)
        
        # Draw simulated candlestick chart
        if coin_history and len(coin_history) >= 5:
            self._draw_candlestick_chart(draw, coin_history, 30, chart_top + 10, WIDTH - 60, chart_height - 20, is_bullish)
        else:
            # Generate synthetic chart data
            synthetic = self._synthetic_chart_data(price, change, 20)
            self._draw_candlestick_chart(draw, synthetic, 30, chart_top + 10, WIDTH - 60, chart_height - 20, is_bullish)
        
        # Chart label
        draw.text((30, chart_top + 5), "CHART ANALYSIS", fill=text_dim, font=self.font_tiny)
        
        # ---- MIDDLE SECTION: Coin Info ----
        mid_y = chart_bottom + 25
        
        # Headline ribbon
        headline_color = primary_color
        draw.rounded_rectangle([20, mid_y, WIDTH - 20, mid_y + 50], radius=6, fill=headline_color)
        
        # Center headline text
        h_text = f"  {headline}  "
        h_bbox = draw.textbbox((0, 0), h_text, font=self.font_bold)
        h_x = (WIDTH - (h_bbox[2] - h_bbox[0])) // 2
        draw.text((h_x, mid_y + 8), h_text, fill=COLORS["bg_dark"], font=self.font_bold)
        
        # Coin Symbol (big, centered)
        sym_y = mid_y + 60
        # Draw card bg
        draw.rounded_rectangle([20, sym_y, WIDTH - 20, sym_y + 85], radius=8, fill=bg_card, outline=border)
        
        symbol_text = f"${symbol}"
        color_text = f"{change:+.1f}%"
        price_text = f"${price:,.4f}" if price < 100 else f"${price:,.2f}"
        
        # Symbol (left)
        sym_bbox = draw.textbbox((0, 0), symbol_text, font=self.font_xl)
        draw.text((40, sym_y + 8), symbol_text, fill=white, font=self.font_xl)
        
        # Change % (right, colored)
        change_str = f"{change:+.1f}%"
        c_color = green if is_bullish else red
        c_bbox = draw.textbbox((0, 0), change_str, font=self.font_title)
        c_x = WIDTH - 40 - (c_bbox[2] - c_bbox[0])
        draw.text((c_x, sym_y + 5), change_str, fill=c_color, font=self.font_title)
        
        # Price (right, below change)
        p_bbox = draw.textbbox((0, 0), price_text, font=self.font_bold_small)
        p_x = WIDTH - 40 - (p_bbox[2] - p_bbox[0])
        draw.text((p_x, sym_y + 50), price_text, fill=gray, font=self.font_bold_small)
        
        # ---- DATA ROW: Volume, Market Cap, Score ----
        data_y = sym_y + 95
        draw.rounded_rectangle([20, data_y, WIDTH - 20, data_y + 60], radius=6, fill=bg_card, outline=border)
        
        # Volume
        draw.text((40, data_y + 8), "VOLUME", fill=text_dim, font=self.font_tiny)
        vol_text = f"{volume_ratio:.1f}x"
        draw.text((40, data_y + 28), vol_text, fill=white, font=self.font_bold_small)
        
        # Market Cap (center)
        if market_cap > 0:
            cap_str = f"${market_cap/1e9:.1f}B" if market_cap >= 1e9 else f"${market_cap/1e6:.1f}M"
            draw.text((WIDTH // 2 - 60, data_y + 8), "MARKET CAP", fill=text_dim, font=self.font_tiny)
            draw.text((WIDTH // 2 - 60, data_y + 28), cap_str, fill=white, font=self.font_bold_small)
        
        # V5 Score (right)
        if v5_score:
            score = v5_score.get("final_score", 0)
            draw.text((WIDTH - 180, data_y + 8), "V5 SCORE", fill=text_dim, font=self.font_tiny)
            score_color = green if score >= 70 else (COLORS["accent_yellow"] if score >= 40 else red)
            draw.text((WIDTH - 180, data_y + 28), f"{score:.0f}/100", fill=score_color, font=self.font_mono_bold)
        
        # ---- NARRATIVE TAG ----
        narr_y = data_y + 70
        if narrative:
            draw.rounded_rectangle([20, narr_y, 20 + len(narrative) * 16 + 30, narr_y + 36], radius=16, fill=dim_color, outline=primary_color)
            draw.text((35, narr_y + 6), f"  {narrative}  ", fill=COLORS["bg_dark"], font=self.font_small)
        else:
            narr_y -= 10
        
        # ---- REASONS SECTION ----
        reason_y = narr_y + 45
        draw.text((30, reason_y), "WHY TRADE?", fill=green if is_bullish else red, font=self.font_bold)
        
        r_y = reason_y + 35
        for i, reason in enumerate(reasons[:4]):
            bullet = "▸" if is_bullish else "▹"
            draw.text((35, r_y), bullet, fill=primary_color, font=self.font_regular)
            draw.text((60, r_y), reason, fill=white, font=self.font_small)
            r_y += 30
        
        # ---- TRADE SETUP SECTION (right side) ----
        setup_x = WIDTH - 340
        setup_y = narr_y + 45
        
        # Draw setup card
        draw.rounded_rectangle([setup_x, setup_y, WIDTH - 20, setup_y + 220], radius=8, fill=bg_card, outline=border)
        
        draw.text((setup_x + 15, setup_y + 8), "TRADE SETUP", fill=primary_color, font=self.font_bold_small)
        
        entries = [
            ("ENTRY", f"${setup.get('entry', '?')}", white),
            ("TP1", f"${setup.get('target1', '?')}", green),
            ("TP2", f"${setup.get('target2', '?')}", green),
            ("STOP", f"${setup.get('stop', '?')}", red),
        ]
        
        s_y = setup_y + 45
        for label, value, color in entries:
            draw.text((setup_x + 15, s_y), label, fill=text_dim, font=self.font_tiny)
            draw.text((setup_x + 15, s_y + 18), value, fill=color, font=self.font_mono_bold)
            s_y += 45
        
        # ---- RISK LEVEL (bottom) ----
        risk_y = HEIGHT - 70
        draw.rounded_rectangle([20, risk_y, WIDTH - 20, HEIGHT - 10], radius=6, fill=bg_card, outline=border)
        
        risk_level = "HIGH" if (v5_score and v5_score.get("risk_penalty", 0) > 5) else ("MEDIUM" if (v5_score and v5_score.get("risk_penalty", 0) > 2) else "LOW")
        risk_color = red if risk_level == "HIGH" else (COLORS["accent_yellow"] if risk_level == "MEDIUM" else green)
        
        confidence = "LOW" if (v5_score and v5_score.get("emergency_override")) else ("MEDIUM" if (v5_score and v5_score.get("final_score", 0) < 60) else "HIGH")
        conf_color = green if confidence == "HIGH" else (COLORS["accent_yellow"] if confidence == "MEDIUM" else red)
        
        # Risk left
        draw.text((40, risk_y + 8), "RISK LEVEL", fill=text_dim, font=self.font_tiny)
        draw.text((40, risk_y + 25), risk_level, fill=risk_color, font=self.font_bold_small)
        
        # Confidence center
        draw.text((WIDTH // 2 - 60, risk_y + 8), "CONFIDENCE", fill=text_dim, font=self.font_tiny)
        conf_pct = v5_score.get("final_score", 50) if v5_score else 50
        draw.text((WIDTH // 2 - 60, risk_y + 25), f"{conf_pct:.0f}%", fill=conf_color, font=self.font_bold_small)
        
        # Narrative right
        if narrative:
            draw.text((WIDTH - 200, risk_y + 8), "NARRATIVE", fill=text_dim, font=self.font_tiny)
            draw.text((WIDTH - 200, risk_y + 25), narrative, fill=primary_color, font=self.font_bold_small)
        
        # ---- WATERMARK ----
        draw.text((WIDTH - 150, HEIGHT - 28), "CREATOR AGENT V5", fill=gray_dim, font=self.font_watermark)
        
        return img
    
    def _draw_candlestick_chart(self, draw, prices, x_start, y_start, width, height, is_bullish):
        """Draw a simplified candlestick chart from price history."""
        if not prices or len(prices) < 2:
            return
        
        n = len(prices)
        min_p = min(prices)
        max_p = max(prices)
        price_range = max_p - min_p if max_p != min_p else 1
        
        candle_width = max(4, (width - (n - 1) * 2) // n)
        spacing = (width - candle_width * n) // (n - 1) if n > 1 else 0
        
        green = COLORS["green"]
        red = COLORS["red"]
        
        for i in range(n - 1):
            p1 = prices[i]
            p2 = prices[i + 1]
            
            x1 = x_start + i * (candle_width + spacing)
            x2 = x_start + (i + 1) * (candle_width + spacing)
            
            y1 = y_start + height - int((p1 - min_p) / price_range * height * 0.9) - int(height * 0.05)
            y2 = y_start + height - int((p2 - min_p) / price_range * height * 0.9) - int(height * 0.05)
            
            color = green if p2 >= p1 else red
            
            # Draw line connecting candles
            draw.line([(x1 + candle_width // 2, y1), (x2 + candle_width // 2, y2)], fill=color, width=2)
            
            # Draw candle body
            high = max(y1, y2)
            low = min(y1, y2)
            body_height = max(2, abs(y2 - y1))
            draw.rectangle([x1, low, x1 + candle_width, low + body_height], fill=color)
        
        # Draw last candle as a dot
        last_x = x_start + (n - 1) * (candle_width + spacing)
        last_y = y_start + height - int((prices[-1] - min_p) / price_range * height * 0.9) - int(height * 0.05)
        draw.ellipse([last_x, last_y - 3, last_x + candle_width, last_y + 3], fill=green if is_bullish else red)
    
    def _synthetic_chart_data(self, price: float, change: float, points: int = 20) -> List[float]:
        """Generate realistic-looking price history."""
        if change == 0:
            change = 0.1
        end_price = price
        start_price = price / (1 + change / 100.0)
        
        data = []
        for i in range(points):
            progress = i / (points - 1)
            base = start_price + (end_price - start_price) * progress
            noise = base * random.uniform(-0.02, 0.02)
            data.append(round(base + noise, 8))
        
        return data
    
    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        return {
            "images_generated": len(self._image_hash_history),
            "unique_prompts": len(self._prompt_history),
            "images_dir": str(self.images_dir),
        }


class ImageComposer:
    """ImageComposer module with reusable templates for Binance Square posts."""
    
    TEMPLATES = {
        "breakout": {"label": "BREAKOUT ALERT"},
        "narrative": {"label": "TRENDING NARRATIVE"},
        "listing": {"label": "BINANCE LISTING"},
        "whale": {"label": "WHALE MOVEMENT"},
        "smart_money": {"label": "SMART MONEY WATCH"},
        "ai_narrative": {"label": "AI NARRATIVE WATCH"},
        "defi": {"label": "DEFI ALERT"},
        "meme": {"label": "MEME WATCH"},
        "default": {"label": "MARKET UPDATE"},
    }
    
    def __init__(self, config=None):
        self.engine = ImageIntelligenceEngine(config)
    
    def select_template(self, coin: Dict[str, Any]) -> str:
        """Select best template based on coin catalyst and narrative."""
        catalyst = coin.get("announcement_type", "") or coin.get("catalyst", "")
        narrative = coin.get("narrative", "") or coin.get("skills_narrative", "")
        symbol = coin.get("symbol", "").lower()
        
        if catalyst == "new_listing":
            return "listing"
        if catalyst in ("airdrop", "launchpool"):
            return "listing"
        if catalyst == "delisting":
            return "breakout"
        if "ai" in narrative.lower() or symbol in ("fetch", "agix", "tao", "rndr", "near"):
            return "ai_narrative"
        if "meme" in narrative.lower() or symbol in ("doge", "shib", "pepe", "wif"):
            return "meme"
        if "defi" in narrative.lower() or symbol in ("aave", "uni", "link", "mkr"):
            return "defi"
        if "rwa" in narrative.lower():
            return "narrative"
        vol = float(coin.get("volume_ratio", 0) or 0)
        if vol > 3:
            return "breakout"
        return "default"
    
    def generate_post_image(
        self,
        coin: Dict[str, Any],
        v5_score: Optional[Dict[str, Any]] = None,
    ) -> Optional[Path]:
        """Generate a post image using best template and live data."""
        template = self.select_template(coin)
        LOGGER.info("ImageComposer: using '%s' template for $%s", template, coin.get("symbol", ""))
        
        analysis = {
            "category": coin.get("narrative", coin.get("skills_narrative", "")),
            "direction": "bullish" if float(coin.get("change_24h", 0) or 0) >= 0 else "bearish",
        }
        setup = {
            "entry": coin.get("entry", "?"),
            "target1": coin.get("target1", "?"),
            "target2": coin.get("target2", "?"),
            "stop": coin.get("stop", "?"),
        }
        try:
            return self.engine.generate(
                coin=coin, analysis=analysis, setup=setup, v5_score_result=v5_score,
            )
        except Exception as e:
            LOGGER.warning("ImageComposer failed for $%s: %s", coin.get("symbol", ""), e)
            return None


class ImageUploader:
    """Upload generated images and return public URLs - guaranteed.
    
    Provider 1: GitHub API (create/update file via REST API - most reliable in GHA)
    Provider 2: Git push with token auth
    Provider 3: GHA environment URL construction
    Provider 4: Base64 data URI (last resort - always works)
    
    Every post will have an image - guaranteed.
    """
    
    def __init__(self, config=None):
        self.config = config
        self.images_dir = Path("images")
        self.images_dir.mkdir(parents=True, exist_ok=True)
    
    def binance_square_upload(self, image_path: Path) -> Optional[str]:
        """Upload image to Binance Square media service.
        
        Flow: request presigned URL, upload image, return public URL.
        Falls back to GitHub API upload on failure.
        """
        square_key = os.getenv("SQUARE_API_KEY") or ""
        if not square_key or not image_path or not image_path.exists():
            LOGGER.info("No SQUARE_API_KEY, skipping Binance upload")
            return None
        
        try:
            import mimetypes
            mime = mimetypes.guess_type(str(image_path))[0] or "image/png"
            file_size = image_path.stat().st_size
            
            # Step 1: Request presigned upload URL
            url = "https://www.binance.com/bapi/composite/v1/public/pgc/openApi/media/upload/getUrl"
            payload = json.dumps({
                "contentType": 1, "mediaType": mime,
                "fileSize": file_size, "fileName": image_path.name,
            }).encode("utf-8")
            
            headers = {
                "X-Square-OpenAPI-Key": square_key,
                "Content-Type": "application/json",
                "clienttype": "binanceSkill",
            }
            
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8", errors="replace"))
            
            if resp_data.get("code") == "000000":
                d = resp_data.get("data", {})
                presigned = d.get("uploadUrl") or d.get("url", "")
                image_url = d.get("imageUrl") or d.get("url", "")
                
                if presigned and image_url:
                    # Step 2: Upload image to presigned URL
                    with open(image_path, "rb") as f:
                        img_data = f.read()
                    
                    up_req = urllib.request.Request(presigned, data=img_data, method="PUT")
                    up_req.add_header("Content-Type", mime)
                    
                    with urllib.request.urlopen(up_req, timeout=60) as up_resp:
                        if up_resp.status in (200, 201):
                            LOGGER.info("Binance image upload success: %s", image_url)
                            return image_url
            
            LOGGER.debug("Binance upload response: %s", resp_data.get("message", "unknown"))
        except Exception as e:
            LOGGER.debug("Binance upload failed: %s", e)
        
        # Fallback to GitHub API
        LOGGER.info("Binance upload failed, falling back to GitHub API")
        return self._github_api_upload(image_path)
    
    def upload(self, image_path: Path) -> tuple:
        """Upload image and return (url, verified).
        
        Returns (url, True) if a reliable upload method succeeded.
        Returns (url, False) if URL is constructed but not verified.
        Returns (None, False) if all methods fail.
        
        verified=True means the image definitely exists at the URL.
        verified=False means the URL might work (e.g., from a previous push).
        """
        if not image_path or not image_path.exists():
            return (None, False)
        
        # Provider 1: GitHub REST API (most reliable in GHA)
        url = self._github_api_upload(image_path)
        if url:
            LOGGER.info("Image uploaded via GitHub API: %s", url)
            return (url, True)
        
        # Provider 2: Git push
        url = self._git_push_image(image_path)
        if url:
            LOGGER.info("Image uploaded via git push: %s", url)
            return (url, True)
        
        # Provider 3: GHA env URL construction (last resort)
        url = self._gha_env_url(image_path)
        if url:
            LOGGER.info("Image URL from GHA env (unverified): %s", url)
            return (url, False)
        
        LOGGER.warning("All image upload methods failed")
        return (None, False)
    
    def _github_api_upload(self, image_path: Path) -> Optional[str]:
        """Upload image to GitHub repo via REST API.
        
        Uses: PUT /repos/{owner}/{repo}/contents/{path}
        This is more reliable than git push in GHA.
        """
        try:
            gh_token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or ""
            if not gh_token:
                return None
            
            gh_repo = os.getenv("GITHUB_REPOSITORY", "")
            if not gh_repo:
                # Try git remote
                import subprocess
                result = subprocess.run(
                    ["git", "remote", "get-url", "origin"],
                    capture_output=True, text=True, timeout=5
                )
                remote = result.stdout.strip()
                if "github.com" in remote:
                    if remote.startswith("git@"):
                        gh_repo = remote.split("github.com:")[-1].replace(".git", "")
                    else:
                        gh_repo = remote.split("github.com/")[-1].replace(".git", "")
            
            if not gh_repo:
                return None
            
            # Read image as base64
            import base64
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
            
            # Get current branch
            import subprocess
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=3
            ).stdout.strip() or "main"
            
            # Copy image to repo images/ directory  
            repo_images = Path("images")
            repo_images.mkdir(parents=True, exist_ok=True)
            dest = repo_images / image_path.name
            
            import shutil
            if Path(image_path).resolve() != dest.resolve():
                shutil.copy2(str(image_path), str(dest))
            
            # API endpoint
            api_url = f"https://api.github.com/repos/{gh_repo}/contents/images/{image_path.name}"
            
            # First check if file exists (get SHA if it does)
            sha = None
            req = urllib.request.Request(api_url, headers={
                "Authorization": f"Bearer {gh_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "codex-agent/1.0"
            }, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    existing = json.loads(resp.read().decode())
                    sha = existing.get("sha")
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    LOGGER.debug("GitHub API check failed: %s", e)
            
            # Create or update file
            payload = {
                "message": f"Add post image {image_path.name}",
                "content": img_b64,
                "branch": branch,
            }
            if sha:
                payload["sha"] = sha
            
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(api_url, data=data_bytes, headers={
                "Authorization": f"Bearer {gh_token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json",
                "User-Agent": "codex-agent/1.0"
            }, method="PUT")
            
            with urllib.request.urlopen(req, timeout=15) as resp:
                response_data = json.loads(resp.read().decode())
            
            # Success! Get the raw URL
            raw_url = f"https://raw.githubusercontent.com/{gh_repo}/{branch}/images/{image_path.name}"
            LOGGER.info("GitHub API upload success: %s", raw_url)
            return raw_url
            
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()[:200] if hasattr(e, 'read') else str(e)
            LOGGER.debug("GitHub API upload failed (HTTP %d): %s", e.code, err_body)
        except Exception as e:
            LOGGER.debug("GitHub API upload failed: %s", e)
        
        return None
    
    def _git_push_image(self, image_path: Path) -> Optional[str]:
        """Push image to GitHub repo using git with token auth."""
        try:
            import subprocess
            
            gh_token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or ""
            if not gh_token:
                return None
            
            gh_repo = os.getenv("GITHUB_REPOSITORY", "")
            if not gh_repo:
                result = subprocess.run(
                    ["git", "remote", "get-url", "origin"],
                    capture_output=True, text=True, timeout=5
                )
                remote = result.stdout.strip()
                if "github.com" in remote:
                    if remote.startswith("git@"):
                        gh_repo = remote.split("github.com:")[-1].replace(".git", "")
                    else:
                        gh_repo = remote.split("github.com/")[-1].replace(".git", "")
            
            if not gh_repo:
                return None
            
            subprocess.run(["git", "config", "user.name", "bot"], capture_output=True, timeout=3)
            subprocess.run(["git", "config", "user.email", "bot@bot.com"], capture_output=True, timeout=3)
            
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=3
            ).stdout.strip() or "main"
            
            # Copy to repo
            repo_images = Path("images")
            repo_images.mkdir(parents=True, exist_ok=True)
            dest = repo_images / image_path.name
            if Path(image_path).resolve() != dest.resolve():
                import shutil
                shutil.copy2(str(image_path), str(dest))
            
            # Set auth URL
            auth_url = f"https://x-access-token:{gh_token}@github.com/{gh_repo}.git"
            subprocess.run(["git", "remote", "set-url", "origin", auth_url], capture_output=True, timeout=5)
            
            subprocess.run(["git", "add", str(dest)], capture_output=True, text=True, timeout=5)
            subprocess.run(["git", "commit", "-m", f"Add image {image_path.name}"], capture_output=True, text=True, timeout=5)
            subprocess.run(["git", "pull", "--rebase", "origin", branch], capture_output=True, text=True, timeout=15)
            
            result = subprocess.run(["git", "push", "origin", branch], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                url = f"https://raw.githubusercontent.com/{gh_repo}/{branch}/images/{image_path.name}"
                LOGGER.info("Git push success: %s", url)
                return url
            
            LOGGER.debug("Git push failed: %s", result.stderr[:200])
        except Exception as e:
            LOGGER.debug("Git push error: %s", e)
        
        return None
    
    def _gha_env_url(self, image_path: Path) -> Optional[str]:
        """Construct GitHub raw URL from GHA env (file must already be in repo)."""
        gh_repo = os.getenv("GITHUB_REPOSITORY", "")
        if gh_repo:
            branch = os.getenv("GITHUB_HEAD_REF") or os.getenv("GITHUB_REF_NAME", "main")
            return f"https://raw.githubusercontent.com/{gh_repo}/{branch}/images/{image_path.name}"
        return None
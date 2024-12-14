import ssl
import pytz
import asyncio
import discord
import aiohttp
import datetime
import pandas as pd
from io import BytesIO
import mplfinance as mpf
from bs4 import BeautifulSoup
from discord.ext import commands
from discord import app_commands
from typing import (
    Literal, 
    Dict, 
    List, 
    Optional, 
    Union
)

class TreasuryRates(commands.Cog):
    def __init__(
            self, 
            bot: commands.Bot
        ) -> None:
        
        self.bot: commands.Bot = bot
        self.graph_link: str = (
            "https://home.treasury.gov/resource-center/data-chart-center/"
            "interest-rates/daily-treasury-rates.csv/2024/all?"
            "type=daily_treasury_yield_curve&field_tdr_date_value=2024&page&_format=csv"
        )
        
        self.updates_links: Dict[str, str] = {
            "5y": "https://www.cnbc.com/quotes/US5Y",
            "7y": "https://www.cnbc.com/quotes/US7Y",
            "10y": "https://www.cnbc.com/quotes/US10Y",
            "20y": "https://www.cnbc.com/quotes/US20Y",
            "30y": "https://www.cnbc.com/quotes/US30Y"
        }
        
        self.bot.loop.create_task(self.periodic_update())
        self.channel_ids: Dict[str, int] = {
            "5y": 1295886755295395980,  
            "7y": 1295886782621028382, 
            "10y": 1295886899793232015,
            "20y": 1297249281673138369,
            "30y": 1297249344835162182
        }
             
        self.update_times = [
            (9, 30), 
            (12, 30),
            (16, 0),
            (19, 0)
        ]
        
        self.timezone = pytz.timezone('America/New_York')
                

    async def periodic_update(self) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = datetime.datetime.now(self.timezone)
            current_time = (now.hour, now.minute)
            if current_time in self.update_times:
                for term in ["5y", "7y", "10y", "20y", "30y"]:
                    channel: Optional[discord.TextChannel] = self.bot.get_channel(
                        self.channel_ids[term]
                    )
                    if channel:
                        await self.fetch_and_send(channel, term)

            next_update = None
            for update_time in self.update_times:
                update_datetime = now.replace(
                    hour=update_time[0], 
                    minute=update_time[1], 
                    second=0, 
                    microsecond=0
                )

                if update_datetime <= now:
                    update_datetime += datetime.timedelta(days=1)
                
                if next_update is None or update_datetime < next_update:
                    next_update = update_datetime
            
            sleep_seconds = (next_update - now).total_seconds()
            await asyncio.sleep(sleep_seconds)
    
    @commands.hybrid_command(
        name="setchannel",
        description="Set the channel for the treasury rates"
    )
    @app_commands.describe(
        term="The term of the treasury rate",
        channel="The channel to send the treasury rates to"
    )
    @commands.has_permissions(administrator=True)
    async def setchannel(
        self, 
        ctx: commands.Context, 
        term: Literal["5y", "7y", "10y", "20y", "30y"], 
        channel: discord.TextChannel
    ) -> None:
        if ctx.channel.id != self.channel_ids[term]:
            await ctx.send(f"Set the channel for the {term.upper()} treasury rates to {channel.mention}")
            self.channel_ids[term] = channel.id
        else:
            await ctx.send(f"The channel for the {term.upper()} treasury rates is already set to {channel.mention}")


    @commands.command()
    async def test(self, ctx: commands.Context) -> None:
        await self.fetch_and_send(ctx, "5y")

    async def fetch_and_send(
        self, 
        channel: Union[discord.TextChannel, commands.Context], 
        term: Literal["5y", "7y", "10y"]
    ) -> None:
        try:
            ssl_context: ssl.SSLContext = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=ssl_context)
            ) as session:
                async with session.get(self.updates_links[term]) as response:
                    if response.status != 200:
                        await channel.send(f"Failed to retrieve data for {term.upper()}.")
                        return
                    html: str = await response.text()

                await asyncio.sleep(2)

                soup: BeautifulSoup = BeautifulSoup(html, 'html.parser')
                
                last_price_tag: Optional[BeautifulSoup] = soup.find(
                    "span", class_="QuoteStrip-lastPrice"
                )
                last_price: str = last_price_tag.text.strip() if last_price_tag else "N/A"
                
                change_down: Optional[BeautifulSoup] = soup.find(
                    "span", class_="QuoteStrip-changeDown"
                )
                change_up: Optional[BeautifulSoup] = soup.find(
                    "span", class_="QuoteStrip-changeUp"
                )
                if change_down:
                    change: str = change_down.text.strip()
                    change_color: discord.Color = discord.Color.red()
                elif change_up:
                    change: str = change_up.text.strip()
                    change_color: discord.Color = discord.Color.green()
                else:
                    change: str = "N/A"
                    change_color: discord.Color = discord.Color.light_grey()

                stats: Dict[str, str] = {}
                summary_stats: List[BeautifulSoup] = soup.find_all(
                    "li", class_="Summary-stat"
                )
                for stat in summary_stats:
                    label: str = stat.find("span", class_="Summary-label").text.strip()
                    value: str = stat.find("span", class_="Summary-value").text.strip()
                    stats[label] = value

                last_trade_time: Optional[BeautifulSoup] = soup.find(
                    "div", class_="QuoteStrip-lastTradeTime"
                )
                last_trade_time: str = (
                    last_trade_time.text.strip() if last_trade_time else "N/A"
                )
                
                async with session.get(self.graph_link) as response:
                    if response.status != 200:
                        await channel.send("Failed to retrieve graph data.")
                        return
                    csv_content: str = await response.text()
                    df: pd.DataFrame = pd.read_csv(
                        BytesIO(csv_content.encode()), parse_dates=["Date"]
                    )
                

                df_sorted: pd.DataFrame = df.sort_values('Date', ascending=False)
                df: pd.DataFrame = df_sorted.head(60) 

                term_column: str = {
                    "5y": "5 Yr",
                    "7y": "7 Yr",
                    "10y": "10 Yr"
                }.get(term, "5 Yr")

                if term_column not in df.columns:
                    await channel.send(f"Data for {term.upper()} not found.")
                    return

                df_sorted: pd.DataFrame = df_sorted.head(60)
                df_sorted: pd.DataFrame = df_sorted.sort_values('Date')
                df_sorted.set_index('Date', inplace=True)
                
                df_sorted['Open'] = df_sorted[term_column]
                df_sorted['High'] = df_sorted[term_column]
                df_sorted['Low'] = df_sorted[term_column]
                df_sorted['Close'] = df_sorted[term_column]
                df_sorted['Open'] = df_sorted['Open'].shift(1)
                df_sorted['High'] = df_sorted[['Open', 'Close']].max(axis=1)
                df_sorted['Low'] = df_sorted[['Open', 'Close']].min(axis=1)

                df_sorted: pd.DataFrame = df_sorted.dropna()

                mpf.plot(
                    df_sorted, 
                    type='candle', 
                    style='charles',
                    title=f"{term.upper()} Yield {len(df_sorted) + 1} Days",
                    ylabel=' ',
                    savefig=dict(
                        fname='yield.png', 
                        dpi=200, 
                        bbox_inches='tight'
                    ),
                    figsize=(10, 5)
                )

                file: discord.File = discord.File('yield.png', filename='yield.png')

                embed: discord.Embed = discord.Embed(
                    title=f"{term.upper()} | {last_trade_time}", 
                    description=f"# {last_price} [{change}]",
                    color=change_color
                )
                
                for key, value in stats.items():
                    embed.add_field(name=key, value=value, inline=True)
                
                embed.set_image(url="attachment://yield.png")
                
                await channel.send(embed=embed, file=file)
        except Exception as e:
            await channel.send(f"An error occurred: {str(e)}")

    @commands.command() 
    @commands.has_permissions(administrator=True)
    async def sync(self, ctx: commands.Context) -> None:
        ctx.bot.tree.copy_global_to(guild=ctx.guild)
        await ctx.bot.tree.sync(guild=ctx.guild)
        await ctx.send("Synced commands")

    @commands.hybrid_command(
        name="help",
        description="Shows information about available commands"
    )
    async def help(self, ctx: commands.Context) -> None:
        embed = discord.Embed(
            title="Treasury Rates Bot Commands",
            description="Here are all the available commands and their descriptions:",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="📊 /setchannel [term] [channel]",
            value="**Admin only:** Set a channel for specific treasury rate updates.\n"
                  "- `term`: Choose from 5y, 7y, 10y, 20y, or 30y\n"
                  "- `channel`: The channel where updates will be sent\n"
                  "Example: `/setchannel 10y #treasury-10y`",
            inline=False
        )

        embed.add_field(
            name="⏰ Automatic Updates",
            value="The bot automatically sends treasury rate updates at:\n"
                  "- 9:30 AM ET\n"
                  "- 12:30 PM ET\n"
                  "- 4:00 PM ET\n"
                  "- 7:00 PM ET",
            inline=False
        )

        embed.add_field(
            name="📈 Update Information",
            value="Each update includes:\n"
                  "- Current yield rate\n"
                  "- Daily change\n"
                  "- Key statistics\n"
                  "- 60-day yield chart",
            inline=False
        )

        embed.set_footer(text="For additional help or issues, please contact an administrator.")
        
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TreasuryRates(bot))

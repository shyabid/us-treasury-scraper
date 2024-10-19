from discord.ext import commands
import discord
import pandas as pd
import mplfinance as mpf
from io import BytesIO
import datetime
import aiohttp
import ssl
from typing import Literal
from bs4 import BeautifulSoup
import asyncio

class TreasuryRates(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.graph_link = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2024/all?type=daily_treasury_yield_curve&field_tdr_date_value=2024&page&_format=csv" 
        self.updates_links = {
            "5y": "https://www.cnbc.com/quotes/US5Y",
            "7y": "https://www.cnbc.com/quotes/US7Y",
            "10y": "https://www.cnbc.com/quotes/US10Y"
        }
        self.bot.loop.create_task(self.periodic_update())
        self.channel_ids = {
            "5y": 1297253290203025418,  
            "7y": 1297253313573683251, 
            "10y": 1297253331839750145
        }

    @commands.hybrid_group(name="treasury", with_app_command=True)
    async def treasury(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Please specify a subcommand: `5y`, `7y`, or `10y`.")

        

    async def periodic_update(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            for term in ["5y", "7y", "10y"]:
                channel = self.bot.get_channel(self.channel_ids[term])
                if channel:
                    await self.fetch_and_send(channel, term)
            await asyncio.sleep(60)  

    # @treasury.command(name="5y")
    # async def treasury_5y(self, ctx):
    #     await ctx.defer()
    #     await self.fetch_and_send(ctx, "5y")

    # @treasury.command(name="7y")
    # async def treasury_7y(self, ctx):
    #     await ctx.defer()
    #     await self.fetch_and_send(ctx, "7y")

    # @treasury.command(name="10y")
    # async def treasury_10y(self, ctx):
    #     await ctx.defer()
    #     await self.fetch_and_send(ctx, "10y")

    async def fetch_and_send(self, channel, term: Literal["5y", "7y", "10y"]):
        try:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
                async with session.get(self.updates_links[term]) as response:
                    if response.status != 200:
                        await channel.send(f"Failed to retrieve data for {term.upper()}.")
                        return
                    html = await response.text()

                await asyncio.sleep(2)

                soup = BeautifulSoup(html, 'html.parser')
                
                last_price_tag = soup.find("span", class_="QuoteStrip-lastPrice")
                last_price = last_price_tag.text.strip() if last_price_tag else "N/A"
                
                change_down = soup.find("span", class_="QuoteStrip-changeDown")
                change_up = soup.find("span", class_="QuoteStrip-changeUp")
                if change_down:
                    change = change_down.text.strip()
                    change_color = discord.Color.red()
                elif change_up:
                    change = change_up.text.strip()
                    change_color = discord.Color.green()
                else:
                    change = "N/A"
                    change_color = discord.Color.light_grey()

                stats = {}
                summary_stats = soup.find_all("li", class_="Summary-stat")
                for stat in summary_stats:
                    label = stat.find("span", class_="Summary-label").text.strip()
                    value = stat.find("span", class_="Summary-value").text.strip()
                    stats[label] = value

                last_trade_time = soup.find("div", class_="QuoteStrip-lastTradeTime")
                last_trade_time = last_trade_time.text.strip() if last_trade_time else "N/A"
                
                async with session.get(self.graph_link) as response:
                    if response.status != 200:
                        await channel.send("Failed to retrieve graph data.")
                        return
                    csv_content = await response.text()
                    df = pd.read_csv(BytesIO(csv_content.encode()), parse_dates=["Date"])
                

                df_sorted = df.sort_values('Date', ascending=False)
                df = df_sorted.head(60) 

                term_column = {
                    "5y": "5 Yr",
                    "7y": "7 Yr",
                    "10y": "10 Yr"
                }.get(term, "5 Yr")

                if term_column not in df.columns:
                    await channel.send(f"Data for {term.upper()} not found.")
                    return

                df_sorted = df_sorted.head(60)
                df_sorted = df_sorted.sort_values('Date')
                df_sorted.set_index('Date', inplace=True)
                
                df_sorted['Open'] = df_sorted[term_column]
                df_sorted['High'] = df_sorted[term_column]
                df_sorted['Low'] = df_sorted[term_column]
                df_sorted['Close'] = df_sorted[term_column]
                df_sorted['Open'] = df_sorted['Open'].shift(1)
                df_sorted['High'] = df_sorted[['Open', 'Close']].max(axis=1)
                df_sorted['Low'] = df_sorted[['Open', 'Close']].min(axis=1)

                df_sorted = df_sorted.dropna()

                mpf.plot(df_sorted, type='candle', 
                         style='charles',
                         title=f"{term.upper()} Yield {len(df_sorted) + 1} Days",
                         ylabel=' ',
                         savefig=dict(
                             fname='yield.png', 
                             dpi=200, 
                             bbox_inches='tight'
                         ),
                         figsize=(10, 5))

                file = discord.File('yield.png', filename='yield.png')

                embed = discord.Embed(
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
    async def sync(self, ctx):
        ctx.bot.tree.copy_global_to(guild=ctx.guild)
        await ctx.bot.tree.sync(guild=ctx.guild)
        await ctx.send("Synced commands")

async def setup(bot):
    await bot.add_cog(TreasuryRates(bot))

from discord.ext import commands
import discord
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
import datetime
import urllib.request
import ssl
from typing import Literal

class TreasuryRates(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def fetch_data(self, year: int) -> pd.DataFrame:
        base_url = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2024/all?type=daily_treasury_bill_rates&field_tdr_date_value={}&page&_format=csv"
        url = base_url.format(year, year)
        try:
            ssl_context = ssl._create_unverified_context()
            with urllib.request.urlopen(url, context=ssl_context) as response:
                data = pd.read_csv(response, parse_dates=['Date'])
            if data.empty:
                return pd.DataFrame()
            return data
        except urllib.error.URLError as e:
            print(f"Failed to retrieve Treasury Bill Rates CSV for year {year}: {e}")
            return pd.DataFrame()

    @commands.hybrid_group(name='treasury')
    async def treasury(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Available subcommands: rates")

    @treasury.group(name='rates')
    async def rates(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Available subcommands: graph, get")

    @rates.command(name='graph')
    async def rates_graph(
        self, 
        ctx: commands.Context, 
        year: int = None
    ):
        """
        Generates a graph of Treasury Bill Rates.
        Usage: ?treasury rates graph [year]
        """
        await ctx.defer()
        if year is None:
            year = datetime.datetime.now().year

        data = await self.fetch_data(year)
        if data.empty:
            await ctx.send(f"Treasury Bill Rates data for year {year} not found.")
            return

        plt.figure(figsize=(10, 6))
        weeks_columns = [col for col in data.columns if 'WEEKS BANK DISCOUNT' in col]

        for column in weeks_columns:
            plt.plot(data['Date'], data[column], label=column.replace(' WEEKS BANK DISCOUNT', ' Weeks'))
        plt.xlabel('Date')

        plt.title(f'US Treasury Bill Rates Graph {year}')
        plt.ylabel('Bank Discount (%)')

        plt.legend()
        plt.tight_layout()

        buf = BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        file = discord.File(buf, filename='treasury_rates_graph.png')
        embed = discord.Embed(title=f'US Treasury Bill Rates Graph {year}', color=0x1a73e8)
        embed.set_image(url='attachment://treasury_rates_graph.png')
        await ctx.reply(file=file, embed=embed)
        plt.close()

    @rates.command(name='get')
    async def rates_get(
        self, 
        ctx, 
        weeks: int = None, 
        date: str = None, 
        year: int = None
    ):
        """
        Retrieves Treasury Bill Rates.
        Usage: ?treasury rates get [weeks] [date] [year]
        - weeks: 4, 8, 13, 17, 26, 52
        - date: YYYY-MM-DD
        - year: YYYY
        If no parameters are given, shows today's rates with change and tomorrow's expectation.
        """
        await ctx.defer()
        if year is None:
            year = datetime.datetime.now().year

        data = await self.fetch_data(year)
        if data.empty:
            await ctx.send(f"Treasury Bill Rates data for year {year} not found.")
            return

        if date:
            try:
                query_date = pd.to_datetime(date)
                if query_date.year != year:
                    data = await self.fetch_data(query_date.year)
                    if data.empty:
                        await ctx.send(f"No data available for year {query_date.year}.")
                        return
            except ValueError:
                await ctx.send("Invalid date format. Please use YYYY-MM-DD.")
                return

            if date:
                available_dates = data['Date']
                closest_date = available_dates[available_dates <= query_date].max()
                if pd.isna(closest_date):
                    closest_date = available_dates.min()
                row = data[data['Date'] == closest_date]
                if row.empty:
                    await ctx.send("No data found for the specified date or closest available date.")
                    return
                query_date = closest_date
            else:
                row = data.iloc[0]
                query_date = row['Date']
        else:
            row = data.iloc[0]
            query_date = row['Date']

        if weeks:
            valid_weeks = [4, 8, 13, 17, 26, 52]
            if weeks not in valid_weeks:
                await ctx.send(f"Invalid weeks value. Choose from: {', '.join(map(str, valid_weeks))}")
                return
            discount_col = f"{weeks} WEEKS BANK DISCOUNT"
            coupon_col = f"{weeks} WEEKS COUPON EQUIVALENT"
            discount = row.get(discount_col)
            coupon = row.get(coupon_col)
            if pd.isna(discount) or pd.isna(coupon):
                await ctx.send(f"No data available for {weeks} weeks.")
                return

            embed = discord.Embed(title=f"{weeks}-Week Treasury Bill Rates", color=0x34a853)
            embed.add_field(name="Date", value=query_date.strftime('%Y-%m-%d'), inline=False)
            embed.add_field(name="Bank Discount", value=f"{discount:.2f}%", inline=True)
            embed.add_field(name="Coupon Equivalent", value=f"{coupon:.2f}%", inline=True)
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(title="Today's Treasury Bill Rates", color=0xfbbc05)
            for week in [4, 8, 13, 17, 26, 52]:
                discount = row.get(f"{week} WEEKS BANK DISCOUNT")
                coupon = row.get(f"{week} WEEKS COUPON EQUIVALENT")
                embed.add_field(
                    name=f"{week}-Week",
                    value=f"Discount: {discount:.2f}%\nCoupon: {coupon:.2f}%",
                    inline=True
                )

            if len(data) > 1:
                yesterday = data.iloc[1]
                changes = {}
                for week in [4, 8, 13, 17, 26, 52]:
                    current = row.get(f"{week} WEEKS BANK DISCOUNT")
                    previous = yesterday.get(f"{week} WEEKS BANK DISCOUNT")
                    if pd.notna(current) and pd.notna(previous):
                        change = ((current - previous) / previous) * 100
                        changes[week] = f"{change:.2f}%"
                    else:
                        changes[week] = "N/A"
                change_str = "\n".join([f"{week}-Week Change: {chg}" for week, chg in changes.items()])
                embed.add_field(name="Change from Yesterday", value=change_str, inline=False)

                expectations = {}
                for week in [4, 8, 13, 17, 26, 52]:
                    recent_data = data[f"{week} WEEKS BANK DISCOUNT"].head(5)  # Last 5 days
                    current = row.get(f"{week} WEEKS BANK DISCOUNT")
                    previous = yesterday.get(f"{week} WEEKS BANK DISCOUNT")
                    if pd.notna(current) and pd.notna(previous):
                        trend = recent_data.diff().mean()
                        expectation = current + trend
                        expectations[week] = f"Expected: {expectation:.2f}%"
                    else:
                        expectations[week] = "N/A"
                expectation_str = "\n".join([f"{week}-Week: {exp}" for week, exp in expectations.items()])
                embed.add_field(name="Expected Tomorrow", value=expectation_str, inline=False)

            await ctx.reply(embed=embed)

    @commands.command()
    async def sync(self, ctx):
        self.bot.tree.copy_global_to(guild=ctx.guild)
        await self.bot.tree.sync(guild=ctx.guild)
        await ctx.send("Synced commands!")

async def setup(bot):
    await bot.add_cog(TreasuryRates(bot))

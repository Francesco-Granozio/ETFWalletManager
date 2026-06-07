from app.services.lang_schwarz_scraper import LangSchwarzScraper


def test_lang_schwarz_parser_does_not_take_currency_from_etf_name():
    html = """
    <html>
      <body>
        <h1>S&P 500 USD (Acc)</h1>
        <p>ISIN: IE000XZSV718</p>
        <div>Bid</div>
        <div>15.712</div>
        <div>Ask</div>
        <div>15.820</div>
        <div>15.740 22:00:00</div>
      </body>
    </html>
    """

    parsed = LangSchwarzScraper()._parse_quote_page(
        html,
        isin="IE000XZSV718",
        page_url="https://www.ls-tc.de/en/etf/123",
    )

    assert parsed["currency"] == "EUR"


def test_lang_schwarz_parser_reads_main_quote_timestamp_without_treating_date_as_price():
    html = """
    <html>
      <body>
        <h1>ISHS VI-BL.R.S.C.U.ETF DL</h1>
        <p>ISIN: IE00BZ1NCS44 | WKN: A2JQ2G</p>
        <div>9,3955</div>
        <div>-</div>
        <div>0,00 %</div>
        <div>06.06. 12:58</div>
        <div>Status:</div>
        <div>closed</div>
        <div>Geld</div>
        <div>9,3360</div>
        <div>€</div>
        <div>Brief</div>
        <div>9,4550</div>
        <div>€</div>
      </body>
    </html>
    """

    parsed = LangSchwarzScraper()._parse_quote_page(
        html,
        isin="IE00BZ1NCS44",
        page_url="https://www.ls-tc.de/de/etf/1372581",
    )

    assert str(parsed["last"]) == "9.3955"
    assert parsed["timestamp"].month == 6
    assert parsed["timestamp"].day == 6

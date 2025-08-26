use reqwest;
use serde::Deserialize;
use tokio;

const ETF_CODES: &[&str] = &[
    "513520", "513350", "513870", "512800", "515000", "513030", "516810", "518880", "513500",
    "512660", "510050", "512000", "513730", "512670", "512400", "513080", "517090", "513800",
    "515750", "520580", "501090", "515710", "516970", "520830", "515220", "513110", "561360",
];

fn to_sina_code(code: &str) -> String {
    let prefix = if code.starts_with('5') { "sh" } else { "sz" };
    format!("{}{}", prefix, code)
}

async fn fetch_etf_kline(code: &str, day: usize) -> Result<Vec<f64>, Box<dyn std::error::Error>> {
    let sina_code = to_sina_code(code);
    let url = format!(
        "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={}&scale=240&ma=no&datalen={}",
        sina_code, day
    );

    let client = reqwest::Client::new();
    let resp = client.get(&url).send().await?.text().await?;

    let data: Vec<SinaKLine> = serde_json::from_str(&resp)?;

    let mut closes = Vec::new();
    for item in data {
        let close: f64 = item.close.parse().map_err(|_| "parse close error")?;
        closes.push(close);
    }

    Ok(closes)
}

#[allow(dead_code)]
#[derive(Deserialize, Debug)]
struct SinaKLine {
    open: String,
    high: String,
    low: String,
    close: String,
    volume: String,
    day: String,
}

fn calculate_downrate(older: f64, newer: f64) -> f64 {
    if older > 0.0 {
        (older - newer) / older * 100.0
    } else {
        0.0
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // cargo run 10 to calculate previous 10 days decline rate
    let args: Vec<String> = std::env::args().collect();
    let day = args
        .get(1)
        .and_then(|s| s.parse::<usize>().ok())
        .unwrap_or(5);

    let mut results = Vec::new();

    for &code in ETF_CODES {
        match fetch_etf_kline(code, day).await {
            Ok(prices) => {
                if prices.len() >= day {
                    let price_pre = prices[0];
                    let price_today = prices[day - 1];

                    if price_today < price_pre {
                        let downrate = calculate_downrate(price_pre, price_today);
                        results.push((code, downrate));
                    }
                } else {
                    eprintln!("Not enough data for {}: got {} days", code, prices.len());
                }
            }
            Err(e) => {
                eprintln!("Failed to fetch data for {}: {}", code, e);
            }
        }
    }

    println!("\n ETF Decline over {} days:", day);
    println!("-----------------------------------------");
    if results.is_empty() {
        println!("No declined ETF");
    } else {
        results.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());
        for (code, rate) in results {
            println!("Code: {} Decline: -{:.2}%", code, rate);
        }
    }

    Ok(())
}

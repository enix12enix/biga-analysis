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

async fn fetch_etf_kline(code: &str, day: usize) -> Result<(Vec<f64>, Option<u16>), Box<dyn std::error::Error>> {
    let sina_code = to_sina_code(code);
    let url = format!(
        "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={}&scale=240&ma=no&datalen={}",
        sina_code, day
    );

    let client = reqwest::Client::new();
    let response = client.get(&url).send().await;
    
    match response {
        Ok(resp) => {
            let status = resp.status().as_u16();
            let text = resp.text().await?;
            
            match serde_json::from_str::<Vec<SinaKLine>>(&text) {
                Ok(data) => {
                    let mut closes = Vec::new();
                    for item in data {
                        match item.close.parse::<f64>() {
                            Ok(close) => closes.push(close),
                            Err(_) => return Ok((Vec::new(), Some(status))),
                        }
                    }
                    Ok((closes, Some(status)))
                }
                Err(_) => {
                    Ok((Vec::new(), Some(status)))
                }
            }
        }
        Err(e) => {
            Err(Box::new(e))
        }
    }
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

fn calculate(older: f64, newer: f64) -> f64 {
    if older > 0.0 {
        (newer - older) / older * 100.0
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
            Ok((prices, status_option)) => {
                if let Some(status) = status_option {
                    if status != 200 {
                        eprintln!("HTTP {} for code: {}", status, code);
                        continue;
                    }
                }

                if prices.len() >= day {
                    let price_pre = prices[0];
                    let price_today = prices[day - 1];

                    if price_today < price_pre {
                        let today_decline_rate = calculate(price_pre, price_today);

                        let half_day_idx = if day > 1 { day / 2 } else { 0 };
                        let half_day_decline_rate = if half_day_idx < prices.len() && day > 1 {
                            let price_half = prices[day - 1 - half_day_idx];
                            calculate(price_pre, price_half)
                        } else {
                            0.0
                        };
                        results.push((code, today_decline_rate, half_day_decline_rate));
                    }
                } else {
                    eprintln!("Not enough data for {}: got {} days", code, prices.len());
                }
            }
            Err(e) => {
                eprintln!("Failed to fetch data for {}: {} (No HTTP status available)", code, e);
            }
        }
    }

    println!("\n ETF Decline over {} days:", day);
    println!("-----------------------------------------");
    if results.is_empty() {
        println!("No ETF data");
    } else {
        let hald_day = day / 2;
        results.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap());
        for (code, rate, new_rate) in results {
            println!(
                "Code: {} | Rate(Today/{} days ago): {:.2}% | Rate({} days ago/{} days ago): {:.2}%",
                code, day, rate, hald_day, day, new_rate
            );
        }
    }

    Ok(())
}
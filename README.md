# NYT Headlines News Feed Printer

A Python daemon that polls the New York Times Top Stories API and prints breaking headlines in the style of an old teletype machine — all caps, paragraph indentation and all. Designed to run on a Raspberry Pi connected to a CUPS-compatible printer (tested with an OKI Microline 520).

## How It Works

1. On each polling cycle (default: every 5 minutes), the daemon fetches the latest articles from the NYT Top Stories API.
2. For each article not yet printed, it builds a payload:
   - The article's **last-updated date**
   - The **headline** in ALL CAPS
   - Up to **three paragraphs** of the article body, each in ALL CAPS with the first line indented five spaces (classic newswire style)
3. The payload is either printed to **stdout** (default) or sent to a CUPS printer via `lp`.
4. Each printed article's URI is saved to a state file so it is never printed twice.

## Requirements

- Python 3.7+
- [`requests`](https://pypi.org/project/requests/) library
- A [New York Times API key](https://developer.nytimes.com/)
- (Optional) A CUPS printer configured on the system for teletype output

## Setup

```bash
# Clone the repo
git clone https://github.com/yourname/nyt-headlines-printer.git
cd nyt-headlines-printer

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install requests
```

## Configuration

Edit `config.json` (created in the project directory):

```json
{
  "nyt_api_key": "YOUR_NYT_API_KEY",
  "section": "home",
  "poll_interval_seconds": 300,
  "printer_name": "oki520",
  "state_path": "printed_ids.json"
}
```

| Key | Description |
|-----|-------------|
| `nyt_api_key` | Your NYT Developer API key |
| `section` | Top Stories section to poll (e.g. `home`, `politics`, `technology`) |
| `poll_interval_seconds` | How often to check for new stories (default: 300 = 5 minutes) |
| `printer_name` | CUPS printer destination name (used with `lp -d`) |
| `state_path` | Path to the JSON file tracking already-printed article URIs |

## Usage

```bash
# Activate the virtual environment first
source venv/bin/activate

# Print to stdout (preview mode)
python3 main.py

# Send output to the configured CUPS printer
python3 main.py --teletype
# or
python3 main.py -t

# Run with debug logging
python3 main.py -d

# Run unit tests
python3 -m unittest test_main.py
```

### Example output

```
2025-11-04
SENATE PASSES SWEEPING CLIMATE BILL IN RARE BIPARTISAN VOTE
     THE SENATE PASSED A $500 BILLION CLIMATE AND INFRASTRUCTURE BILL TUESDAY,
WITH SUPPORT FROM BOTH SIDES OF THE AISLE IN A RARE DISPLAY OF BIPARTISAN
COOPERATION.
     THE LEGISLATION, WHICH NOW HEADS TO THE HOUSE, WOULD FUND RENEWABLE ENERGY
PROJECTS ACROSS ALL 50 STATES AND IS EXPECTED TO CREATE HUNDREDS OF THOUSANDS
OF JOBS OVER THE NEXT DECADE.
     PRESIDENT JOHNSON PRAISED THE VOTE AS "A HISTORIC MOMENT FOR OUR PLANET
AND OUR CHILDREN'S FUTURE."
```

## Running as a Service (Raspberry Pi)

To run the daemon automatically on boot, install the included systemd service unit:

```bash
sudo cp nyt-printer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable nyt-printer
sudo systemctl start nyt-printer

# Check logs
journalctl -u nyt-printer -f
```

You may need to adjust the `WorkingDirectory` and `ExecStart` paths in `nyt-printer.service` to match your installation.

## Project Structure

```
nyt-headlines-printer/
├── main.py              # Main daemon script
├── config.json          # Configuration (API key, printer, etc.)
├── printed_ids.json     # State file — auto-created at runtime
├── nyt-printer.service  # systemd unit for running as a service
├── venv/                # Python virtual environment
└── README.md            # This file
```

## License

MIT

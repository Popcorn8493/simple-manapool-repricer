# Simple ManaPool Repricer

Automatically update your ManaPool inventory prices based on current market data.

## What This Does

This script connects to your ManaPool account and automatically updates the
prices of all cards in your inventory based on current market prices. It's
designed to help you stay competitive without manually checking and updating
prices.

## Prerequisites

### 1. Install Python

If you don't have Python installed:

- **Windows**: Download from
  [python.org](https://www.python.org/downloads/)
  - During installation, check the box that says "Add Python to PATH"
- **Mac**: Usually pre-installed. If not, download from
  [python.org](https://www.python.org/downloads/)
- **Linux**: Usually pre-installed. If not, use your package manager
  (e.g., `sudo apt install python3`)

To verify Python is installed, open a terminal/command prompt and type:

```bash
python --version
```

or

```bash
python3 --version
```

You should see something like `Python 3.11.0` or similar.

### 2. Get Your ManaPool API Credentials

You need two things from your ManaPool account:

- Your email address
- An API access token

To get your API token, log into your ManaPool account and navigate to
<https://manapool.com/seller/integrations/manapool-api>

## Installation

1. **Download or clone this project** to your computer

2. **Open a terminal/command prompt** in the project folder

3. **Install the required Python packages** by running:

   ```bash
   pip install -r requirements.txt
   ```

   If that doesn't work, try:

   ```bash
   python -m pip install -r requirements.txt
   ```

   or on Mac/Linux:

   ```bash
   python3 -m pip install -r requirements.txt
   ```

## Configuration

Before running the script, you need to configure your settings and add your
ManaPool credentials.

### 1. Configure API Credentials (.env file)

1. **Copy the example environment file**:

   ```bash
   cp .env.example .env
   ```

   On Windows (PowerShell):

   ```powershell
   Copy-Item .env.example .env
   ```

   On Windows (Command Prompt):

   ```cmd
   copy .env.example .env
   ```

2. **Edit the `.env` file** and add your ManaPool credentials:

   ```text
   API_EMAIL=your-email@example.com
   API_TOKEN=your-access-token-here
   ```

   Replace `your-email@example.com` with your actual ManaPool email and
   `your-access-token-here` with your actual API token.

   **Important**: The `.env` file is already in `.gitignore` and will not be
   committed to version control. This keeps your credentials safe.

### 2. Configure Pricing Settings (config.json)

The `config.json` file contains all the pricing settings. You can edit it
with any text editor:

```json
{
  "api": {
    "base_url": "https://manapool.com/api/v1"
  },
  "pricing": {
    "dry_run": true,
    "strategy": "lp_plus",
    "lp_floor_percent": 100.0,
    "min_price": 0.01,
    "max_reduction_percent": 5.0,
    "price_adjustment_factor": 1.042
  }
}
```

**Key settings**:

- `dry_run` - When `true`, the script will show you what changes it would
  make without actually updating your prices. **Keep this as `true` for your
  first run!**
- `strategy` - Choose how prices are calculated:
  - `"lp_plus"` - Conservative pricing (recommended for most users)
  - `"nm_with_floor"` - Uses NM price but won't go below LP+ (safest)
  - `"average"` - Average of NM and LP+ prices
  - `"nm_only"` - Uses only NM price (more aggressive)
  - `"general_low"` - Uses general market price (most competitive)
- `lp_floor_percent` - LP+ floor percentage (100 = strict floor)
- `min_price` - Minimum price in dollars
- `max_reduction_percent` - Maximum price drop per run (%)
- `price_adjustment_factor` - API prices are multiplied by this factor

## Running the Script

1. **Open a terminal/command prompt** in the project folder

2. **Run the script**:

   ```bash
   python repricer.py
   ```

   If that doesn't work, try:

   ```bash
   python3 repricer.py
   ```

3. **Review the output**:

   - The script will show you what it's doing step by step
   - It will display a preview of price changes
   - If `DRY_RUN = True`, it won't actually change anything

4. **Apply changes** (when ready):
   - Set `"dry_run": false` in `config.json`
   - Run the script again
   - When prompted, type `yes` to confirm the changes

## What to Expect

The script will:

1. Fetch your inventory from ManaPool
2. Get current market prices
3. Calculate new prices based on your settings
4. Show you a preview of all changes
5. Ask for confirmation before applying (if not in dry-run mode)
6. Save a detailed report to a JSON file

## Safety Features

- **Dry Run Mode**: Test the script without making any changes
- **Maximum Reduction Cap**: Limits how much prices can drop in a single run
  (default: 5%)
- **Minimum Price**: Prevents prices from going below a certain amount
  (default: $0.01)
- **Confirmation Required**: You must type "yes" to apply changes

## Troubleshooting

### "Python is not recognized"

- Make sure Python is installed and added to your PATH
- Try using `python3` instead of `python`

### "Module not found" errors

- Make sure you ran `pip install -r requirements.txt`
- Try: `python -m pip install --upgrade pip` then install again

### "Configuration Error - Missing API Credentials"

- Make sure you created a `.env` file (copy from `.env.example`)
- Make sure you set `API_EMAIL` and `API_TOKEN` in your `.env` file
- Check that there are no extra spaces or quotes around your credentials in
  `.env`
- Make sure the `.env` file is in the same directory as `repricer.py`

### "Configuration Error - config.json not found"

- Make sure `config.json` exists in the project directory
- If it's missing, create it using the example structure shown in the
  Configuration section

### Script runs but shows "No price data" for all cards

- Check that your API token is valid and has the correct permissions
- Verify your ManaPool account has inventory items

## Files Created

The script creates a JSON report file each time it runs:

- `price_updates_YYYYMMDD_HHMMSS.json` - Contains detailed information about
  all price changes

## Need Help?

If you encounter issues:

1. Make sure all prerequisites are installed correctly
2. Verify your API credentials are correct in the `.env` file
3. Make sure `config.json` exists and is valid JSON
4. Try running with `"dry_run": true` in `config.json` first to see what would
   happen
5. Check the error messages - they usually tell you what's wrong

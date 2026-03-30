# PiGame

`PiGame` is a foundation for a passive RPG pet device built around:

- `Raspberry Pi Zero 2 W`
- `Waveshare e-Paper`
- `UPS Lite v1.3`

The game is designed for a device without buttons. The character lives on its own, grows over time, enters dungeons, finds loot, unlocks roles, and can later sync with nearby devices for party play and trade.

## Recommended OS

Start with `Raspberry Pi OS Lite (64-bit)`.

Reason:

- best compatibility with Raspberry Pi SPI and GPIO ecosystem
- lower overhead than a full Ubuntu desktop image
- easier service setup for a background game daemon

Ubuntu can be supported later, but first implementation should target Raspberry Pi OS Lite.

## What is implemented now

- game state and save file format
- autonomous tick-based progression
- dungeons, scaling enemies, loot, consumables
- role specialization unlocks
- placeholder "mini AI" flavor summaries
- text renderer abstraction for the future e-ink screen
- autonomous runtime loop for Raspberry Pi
- optional Waveshare adapter with fallback snapshot mode
- battery state reflected in save data and on-screen status
- safe progress save before low-battery shutdown
- local HTTP manager for editing state from a PC

For `UPS-Lite`, the battery reader now targets `MAX17040G` on I2C.
Default runtime settings assume:

- I2C bus `1`
- device address `0x62`

Your board may expose either:

- `0x62` with `CW2015`
- `0x36` with `MAX17040`

The project now supports both, and your reported scan indicates `0x62`.

## Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

For Raspberry Pi hardware rendering, `Pillow` is required and is now installed by the project automatically.

## Run

Initialize a save:

```powershell
pigame init --name Piko
```

Advance the simulation:

```powershell
pigame run --ticks 12
```

Render the current screen:

```powershell
pigame render
```

Start the local management server:

```powershell
pigame-manager --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080`.

Run the autonomous device loop:

```powershell
pigame daemon --renderer console --tick-seconds 5 --max-ticks 6
```

Run with low-battery protection:

```powershell
pigame daemon --renderer waveshare --low-battery-percent 15 --critical-battery-percent 5 --shutdown-command "sudo systemctl poweroff"
```

If you want to force the UPS reader explicitly:

```powershell
pigame daemon --renderer waveshare --battery-backend cw2015 --battery-bus 1 --battery-address 0x62
```

Check hardware renderer availability:

```powershell
pigame hardware-check
```

## Architecture

- `src/pigame/models.py` - state, stats, inventory, party and world models
- `src/pigame/core.py` - progression and simulation engine
- `src/pigame/storage.py` - JSON save persistence
- `src/pigame/device.py` - renderer and peer sync abstractions
- `src/pigame/runtime.py` - long-running autonomous device loop
- `src/pigame/desktop_server.py` - desktop management UI and API
- `src/pigame/cli.py` - command-line entry point
- `deploy/systemd/pigame.service` - service template for Raspberry Pi OS

## Next hardware steps

1. Replace the text renderer with a real Waveshare e-ink driver wrapper.
2. Add actual bitmap drawing through Pillow into the Waveshare adapter.
3. Detect charging state from the UPS hardware, if the board exposes it through an extra pin or companion controller.
4. Add BLE or Wi-Fi peer discovery and signed state exchange.
5. Add USB gadget or local AP mode for easier PC management.

## Raspberry Pi service setup

Copy the repository onto the Pi, install it, then:

```bash
sudo cp deploy/systemd/pigame.service /etc/systemd/system/pigame.service
sudo systemctl daemon-reload
sudo systemctl enable --now pigame.service
```

If needed, change the paths in `deploy/systemd/pigame.service` from `/home/pi/pigame` to your real project path.

## Pi preparation notes

On Raspberry Pi OS Lite, enable I2C first:

```bash
sudo raspi-config
```

Then install one SMBus package:

```bash
sudo apt install -y python3-smbus i2c-tools
```

For the Waveshare Python stack, the vendor wiki also lists these useful packages:

```bash
sudo apt install -y python3-pip python3-pil python3-numpy python3-gpiozero
sudo pip3 install spidev
```

You can confirm that the fuel-gauge is visible on the Pi with:

```bash
i2cdetect -y 1
```

Expected UPS-Lite gauge address on your board: `0x62`.

## E-ink refresh notes

According to the Waveshare manual for the 2.13 inch panel:

- prefer refresh intervals of at least `180` seconds
- do not keep the panel powered unnecessarily between updates
- put the display into sleep after drawing

The runtime defaults were updated to `180` seconds to match that guidance.

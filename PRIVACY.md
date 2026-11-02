# Privacy

GT Pilot runs entirely on your computer (Mac or Windows PC).

**What it touches on your machine**
- The BOSS GT-1, over USB (MIDI to read and change patches, USB audio when Claude listens to measure level and noise).
- The parameter map inside BOSS TONE STUDIO for GT-1, copied to `~/Library/Application Support/GT Pilot` on a Mac or `%APPDATA%\GT Pilot` on Windows.
- Patch backups, saved in the same folder before any slot is overwritten.

**Audio.** When you ask Claude to listen, a few seconds of the GT-1 output are recorded and turned into numbers (loudness, brightness, noise). The recording is not stored or sent anywhere; only the numbers go back into the conversation.

**Network.** One request per session to `https://allankirsten.com/lab/gt-pilot/latest.json` to check for a newer version, made only after GT Pilot connects to your pedal. The request says three things and nothing else: the GT Pilot version, the system (`mac` or `windows`) and, the very first time on a computer, the word `first`. It carries no identifier, so we can count how many people start using GT Pilot and on which system, but cannot tell anyone apart or link two sessions to the same person. Nothing about you, your pedal or your patches is sent, and IP addresses are not stored. You can turn it off in the extension settings (**Check for new versions**).

**Your conversation** is between you and Claude, under Anthropic's terms. GT Pilot adds tool results (patch names, parameter values, measurements) to it, nothing else.

**No identifiers, no analytics, no accounts.** Besides the anonymous count above, nothing is collected.

Questions: open an issue at https://github.com/allankirsten/gt-pilot/issues.

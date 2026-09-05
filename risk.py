"""Risk acknowledgement shown when the HH over-temperature trip is raised above stock."""

PHRASE = "I ACCEPT THE RISK"

TEXT = (
    "You are about to raise the HH over-temperature trip above the factory value.\n"
    "\n"
    "The HH trip is the ONLY over-temperature protection in this dryer's firmware.\n"
    "Above it, nothing in software limits the chamber temperature: the heater\n"
    "runs until the setpoint is reached or the hardware fails. This can:\n"
    "\n"
    "  - deform or melt the filament and the spool\n"
    "  - deform or melt the dryer's plastic enclosure\n"
    "  - overheat the heater MOSFET (Q4), which has no heatsink\n"
    "  - cause a fire\n"
    "\n"
    "This voids any warranty. You are responsible for choosing sane limits,\n"
    "verifying your wiring, and not leaving a modified dryer unattended until\n"
    "you have watched it behave. The author accepts no liability for damage or\n"
    "injury.\n"
)


def cli_flag_text() -> str:
    return "acknowledge the risks of raising the HH trip (required when --hh is above stock)"

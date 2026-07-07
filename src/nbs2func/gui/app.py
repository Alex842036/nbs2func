from __future__ import annotations

from .wizard import WizardApp


def main() -> None:
    app = WizardApp()
    app.mainloop()


if __name__ == "__main__":
    main()

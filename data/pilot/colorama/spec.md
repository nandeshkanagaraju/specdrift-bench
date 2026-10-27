# colorama specification

## Color codes

- **R01** `Fore.RED` MUST be the ANSI escape sequence `ESC[31m`.
- **R02** `Back.RED` MUST be the ANSI escape sequence `ESC[41m`.
- **R03** `Style.RESET_ALL` MUST be the ANSI escape sequence `ESC[0m`.
- **R04** `Fore.RESET` MUST be the ANSI escape sequence `ESC[39m`.

## Cursor and screen

- **R05** `Cursor.POS` MUST place the row before the column in the sequence it returns.
- **R06** `clear_screen` MUST clear the whole screen when called without a mode.
- **R07** `set_title` MUST wrap the title in an operating-system-command sequence that ends with the bell character.

## Stripping

- **R08** `AnsiToWin32.write` MUST remove ANSI color sequences from the text when `strip` is true.
- **R09** `AnsiToWin32` MUST strip ANSI sequences by default when the wrapped stream is not a terminal.
- **R10** `AnsiToWin32.should_wrap` MUST be true when any of `convert`, `strip` or `autoreset` is true.

## Reset

- **R11** `AnsiToWin32.reset_all` MUST write the reset-all sequence to a stream that is not being stripped.
- **R12** `AnsiToWin32.write` MUST reset the colors after each write when `autoreset` is true.

## Parameters

- **R13** `AnsiToWin32.extract_params` MUST default a missing cursor position parameter to 1.
- **R14** `AnsiToWin32.extract_params` MUST default the parameters of the `J`, `K` and `m` commands to 0.
- **R15** `AnsiToWin32.extract_params` MUST default the parameters of the `A`, `B`, `C` and `D` commands to 1.

## Initialisation

- **R16** `init` MUST raise `ValueError` when `wrap` is false and another option is true.
- **R17** `wrap_stream` MUST return the stream itself when `wrap` is false.

## Windows attributes

- **R18** `WinTerm.get_attrs` MUST combine the foreground, the background times 16 and the style into one attribute value.
- **R19** `WinTerm.set_attrs` MUST read the background color from bits 4 to 6 of the attribute value.
- **R20** `WinTerm.set_attrs` MUST read the foreground color from the low 3 bits of the attribute value.

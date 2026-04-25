# id-me-otpauth

An unofficial tool to use standard TOTP authenticator apps with the ID.me service.

ID.me used to directly support any TOTP authenticator app, but removed the option for doing so when they introduced their own mobile apps. However, under the hood, TOTP is still used. id-me-otpauth talks to the ID.me API directly to obtain the TOTP information needed to use any normal TOTP authenticator app.

## Usage

1. Ensure that [Python](https://www.python.org/) and [`uv`](https://docs.astral.sh/uv/) are installed.

    uv will automatically install the needed dependencies. If you prefer not to use uv, then install the following dependencies manually:

    * cryptography
    * pydantic
    * qrcode
    * requests

2. Log into ID.me and go to the [account settings](https://account.id.me/signin/security) to add a new authenticator app.

3. Decode the QR code shown by ID.me. The easiest way is to use a phone and copy the resulting URL. The URL should look like the following:

    ```
    https://account.id.me/mobile/generator/XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX/YYYYYY
    ```

    Alternatively, the QR code can be decoded on a computer by right clicking and saving the image and then decoding it with [zbar](https://zbar.sourceforge.net/):

    ```bash
    zbarimg Untitled.svg
    ```

4. Run id-me-otpauth with the URL from the QR code:

    ```
    uv run id-me-otpauth.py https://account.id.me/mobile/generator/XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX/YYYYYY
    ```

    This will print out the standard TOTP information as both an `otpauth://` URL as well as a QR code.

    **NOTE**: If the command fails, you must start from the beginning because activation URLs can only be used once.

5. Add the account to your favorite TOTP authenticator app.

6. That's it!

## License

id-me-otpauth is licensed under GPL-3.0-only. Please see [`LICENSE`](./LICENSE) for the full license text.

#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Andrew Gunnerson
# SPDX-License-Identifier: GPL-3.0-only

import argparse
import base64
import dataclasses
import random
import sys
from typing import Literal, Self

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import BaseModel
import qrcode
import requests


# These can all be static values.
ANDROID_VERSION = '16'
ANDROID_API = 36
DEVICE_MANUFACTURER = 'Google'
DEVICE_MODEL = 'Pixel 10 Pro XL'
DEVICE_NAME = 'AUTHN'
APK_VERSION_NAME = '1.12.0-2025082916'
APK_VERSION_CODE = '2025082916'

BASE_URL = 'https://api.id.me/api/mobile/v3'


def raise_for_status_with_body(r: requests.Response):
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        raise requests.HTTPError(f'{e}: {r.text}', response=r) from None


@dataclasses.dataclass
class ActivationInfo:
    token: str
    code: str

    @classmethod
    def from_url(cls, url: str) -> Self:
        pieces = url.split('/')

        if not (
            len(pieces) == 7
            and pieces[0] == 'https:'
            and not pieces[1]
            and pieces[2] == 'account.id.me'
            and pieces[3] == 'mobile'
            and pieces[4] == 'generator'
        ):
            raise ValueError(f'Unsupported activation URL: {url}')

        return cls(token=pieces[5], code=pieces[6])


def register_device(session: requests.Session, device_name: str, device_uuid: str):
    # This is required for x-device-uuid to be accepted by further API calls.
    r = session.post(f'{BASE_URL}/devices/register', json={
        'platform': 'Android',
        'version': str(ANDROID_API),
        'revision': APK_VERSION_NAME,
        'model': DEVICE_MODEL,
        'name': device_name,
        'uuid': device_uuid,
        # This is normally a firebase token obtained from
        # https://android.clients.google.com/c2dm/register3, but it is not
        # required.
        'token': '',
    })
    raise_for_status_with_body(r)

    data = r.json()

    if data['upgrade']:
        raise ValueError(f'Server requires newer client version than: {APK_VERSION_NAME}')


class UserInfo(BaseModel):
    uuid: str
    email: str


def activate_device(session: requests.Session, activation: ActivationInfo) -> UserInfo:
    # It doesn't matter which public key we use. It just needs to be valid.
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()
    public_key_pem = public_key.public_bytes(
       encoding=serialization.Encoding.PEM,
       format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    r = session.post(f'{BASE_URL}/devices/activate', json={
        'token': activation.token,
        'code': activation.code,
        # Yes, this is base64-encoded PEM for some reason. PEM is already
        # base64-encoded DER...
        'public_key': base64.b64encode(public_key_pem).decode('ascii'),
    })
    raise_for_status_with_body(r)

    return UserInfo(**r.json())


class KeyHandle(BaseModel):
    handle: str
    name: str
    revoked: str
    revoked_at: str
    type: str


class EventLocation(BaseModel):
    city: str | None = None
    country: str | None = None
    ipaddress: str | None = None
    state: str | None = None


class EventMetadata(BaseModel):
    consumer: str
    platform: str


class Event(BaseModel):
    created_at: str
    expires_at: str
    kind: Literal['registration', 'confirmation']
    location: EventLocation
    metadata: EventMetadata
    status: Literal['accepted', 'denied', 'failed', 'waiting', 'initialized']
    type: str | None = None
    uuid: str


class Events(BaseModel):
    keys: list[KeyHandle]
    registration: list[Event]
    confirmation: list[Event]


def get_pending_events(session: requests.Session) -> Events:
    r = session.post(f'{BASE_URL}/events', json={
        'handles': [],
    })
    raise_for_status_with_body(r)

    return Events(**r.json())


class OtpAuthInfo(BaseModel):
    success: bool
    code: str | None = None
    message: str | None = None
    qr_code: str


def generate_otpauth(session: requests.Session, activation: ActivationInfo, uuid: str) -> str:
    r = session.post(f'{BASE_URL}/events/generator/{uuid}/registrations', json={
        'token': activation.token,
        'code': activation.code,
    })
    raise_for_status_with_body(r)

    data = OtpAuthInfo(**r.json())

    if not data.success:
        raise ValueError(f'Failed to obtain otpauth URL: [{data.code}] {data.message}')

    return data.qr_code


def log(*args, **kwargs):
    kwargs['file'] = sys.stderr
    print(*args, **kwargs)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'activation',
        type=ActivationInfo.from_url,
        help='Activation URL',
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # This is normally set to Android's Settings.Secure.ANDROID_ID, which is a
    # unique, but persistent, number associated with the device, Android user,
    # and the app's signing key. From the app's point of view, it's completely
    # opaque.
    device_uuid = random.randbytes(8).hex()

    session = requests.Session()
    session.headers['user-agent'] = f'me.id.auth/{APK_VERSION_NAME}/{APK_VERSION_CODE} (Android {ANDROID_VERSION}/API {ANDROID_API}; {DEVICE_MODEL}/{DEVICE_MANUFACTURER})'
    session.headers['x-device-name'] = DEVICE_NAME
    session.headers['x-device-uuid'] = device_uuid

    register_device(session, DEVICE_NAME, device_uuid)
    user = activate_device(session, args.activation)

    # All further calls require authentication as the user.
    session.headers['x-device-user'] = user.uuid
    log(f'Activating TOTP for user: {user.email}')

    events = get_pending_events(session)
    reg = next(
        (
            r for r in events.registration
            if r.kind == 'registration' and r.status == 'waiting'
        ),
        None,
    )
    if not reg:
        raise ValueError('No pending TOTP registration event found')

    log(f'Found pending registration from {reg.created_at} on {reg.metadata.platform!r}')

    otpauth = generate_otpauth(session, args.activation, reg.uuid)
    print(otpauth)

    qr = qrcode.QRCode()
    qr.add_data(otpauth)
    qr.print_ascii(sys.stderr)


if __name__ == '__main__':
    main()

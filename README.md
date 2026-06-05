# Socialplace

## Introduction — What is Socialplace?

Socialplace is an old social network that has been shut down and is now open source. It is a place where you can chat, post, exchange messages, and much more.

## How to use it

You can download this project and run it on your own server to use it with your community or even your company.

The site runs on port `5015`.

The admin panel is accessible via `/uwuplace` (an uncommon name chosen as a small security touch).

### Some useful queries to know:

Add admin role:

`UPDATE user SET is_admin = 1 WHERE username = 'user';`

Add verified role:

`UPDATE user SET is_verified = 1 WHERE username = 'user';`

The user ban command is available in the admin panel.

Do not forget to create your symbolic link as follows, for your USB drive: `ln -s /media/usb/uploads uploads`

### Recommendations
- Use Cloudflare Turnstile by adding your Turnstile secret key to protect your site from spam.
- Change your secret key.
- Update your `/tos` and `/conf` pages.

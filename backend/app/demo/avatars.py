"""Illustrated SVG portraits for the synthetic Austin demo people, drawn on request (no image files stored).

Same drawing as scripts/generate_demo_avatars.py. Appearance is picked at random from the person's id, never inferred
from their name or any identity attribute.
"""

import hashlib
import random

BACKGROUNDS = ["#FAD5E5", "#DDD7FC", "#FFE2C1", "#CDEBE8", "#D6E6FC", "#F4D7EE", "#E2DDF7", "#FFDCCB", "#F9D8D2", "#D4E9DA", "#D8E2FA"]
SKINS = ["#F3C5A1", "#F1B68F", "#E5AB85", "#D99B73", "#BE8057", "#B97852", "#AD704C", "#A76B4B", "#875332", "#6B4128"]
HAIRS = ["#733F2E", "#30252E", "#49332C", "#292A30", "#50382B", "#7D3C28", "#27242A", "#AF5732", "#63432D", "#C9A26B", "#8A8A8A"]
SHIRTS = ["#A42B72", "#6550B9", "#C55735", "#227B73", "#4565B4", "#944C99", "#7251AC", "#A3482E", "#BD5076", "#36775E", "#5263AB"]
STYLES = ["bob", "waves", "long", "bun", "crop", "sweep", "curls"]
ACCESSORIES = ["none", "none", "none", "glasses", "earrings", "beard"]


# Style pools for the self-reported gender a person chose (never inferred). Unset / other answers use every style, no beard.
POOLS = {
    "woman": (["bob", "waves", "long", "bun", "curls"], ["none", "none", "none", "glasses", "earrings"]),
    "man": (["crop", "sweep", "curls"], ["none", "none", "none", "glasses", "beard"]),
}
ANY = (STYLES, ["none", "none", "none", "glasses", "earrings"])


def avatar_svg(key: str, gender: str | None = None) -> str:
    """Portrait for `key`. Without a gender this is the original demo drawing; with one it draws from that pool."""
    rng = random.Random(int(hashlib.sha256(key.encode()).hexdigest()[:12], 16))
    if gender is None:
        style, accessory = rng.choice(STYLES), rng.choice(ACCESSORIES)
        if accessory == "beard" and style in ("bob", "waves", "long", "bun"):
            accessory = "none"
    else:
        styles, accessories = POOLS.get(gender, ANY)
        style, accessory = rng.choice(styles), rng.choice(accessories)
    return portrait(key, rng.choice(BACKGROUNDS), rng.choice(SKINS), rng.choice(HAIRS), rng.choice(SHIRTS), style, accessory)


def portrait(key, background, skin, hair, shirt, style, accessory):
    long_hair = style in ('bob', 'waves', 'long', 'bun')
    back = ''
    if long_hair:
        bottom = 91 if style == 'bob' else 116
        back = f'<path d="M31 64Q28 20 64 21Q101 20 98 66L100 {bottom}Q64 {bottom+12} 28 {bottom}Z" fill="{hair}"/>'
    if style == 'bun':
        back += f'<circle cx="65" cy="23" r="18" fill="{hair}"/>'
    fringe = {
        'bob': 'M32 61Q27 23 62 23Q98 21 96 61Q81 52 76 38Q59 58 32 61Z',
        'waves': 'M31 64Q23 37 39 29Q47 15 63 23Q83 15 94 33Q105 47 96 65L83 49Q70 51 63 35Q55 54 34 56Z',
        'long': 'M32 62Q27 22 63 23Q99 20 97 65L86 54Q73 45 69 34Q55 53 32 62Z',
        'bun': 'M32 62Q29 27 63 27Q96 27 97 61L86 53Q65 50 56 37Q49 55 32 62Z',
        'crop': 'M33 59L33 42Q32 25 51 25L80 25Q97 27 96 45L96 60L86 51L85 43Q60 49 43 43L42 54Z',
        'sweep': 'M33 61Q25 40 40 30Q61 13 88 28Q105 40 95 63L84 48Q62 51 51 39Q47 54 33 61Z',
        'curls': 'M32 62Q22 52 30 42Q24 30 39 27Q45 15 58 23Q70 13 80 25Q96 20 99 36Q110 45 98 58L86 54L83 42Q64 51 43 44L42 58Z',
    }[style]
    extras = ''
    if accessory == 'earrings':
        extras = '<g fill="none" stroke="#F8C45D" stroke-width="3"><ellipse cx="33" cy="78" rx="4" ry="6"/><ellipse cx="95" cy="78" rx="4" ry="6"/></g>'
    if accessory == 'glasses':
        extras = '<g fill="#FFFFFF" fill-opacity=".15" stroke="#343447" stroke-width="2.5"><rect x="39" y="59" width="20" height="16" rx="6"/><rect x="69" y="59" width="20" height="16" rx="6"/><path d="M59 65Q64 61 69 65" fill="none"/></g>'
    if accessory == 'beard':
        extras = f'<path d="M40 78Q43 100 64 101Q85 100 88 78L79 88Q64 96 49 87Z" fill="{hair}"/><path d="M56 86Q64 91 72 86" fill="none" stroke="#F5C2A0" stroke-width="2.5" stroke-linecap="round"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
<defs><clipPath id="portrait"><circle cx="64" cy="64" r="64"/></clipPath></defs>
<g clip-path="url(#portrait)">
<path fill="{background}" d="M0 0h128v128H0z"/>
<circle cx="109" cy="20" r="33" fill="#FFF" opacity=".24"/>
{back}
<path d="M16 133Q17 103 47 100H81Q111 104 112 133" fill="{shirt}"/>
<path d="M53 88H75V104Q65 116 53 104Z" fill="{skin}"/>
<path d="M53 90Q64 101 75 90V99Q64 106 53 99Z" fill="#522F29" opacity=".13"/>
<g fill="{skin}"><ellipse cx="35" cy="69" rx="7" ry="10"/><ellipse cx="93" cy="69" rx="7" ry="10"/><path d="M35 54Q36 31 64 31Q92 31 93 54L90 76Q85 98 64 99Q43 98 38 76Z"/></g>
<path d="{fringe}" fill="{hair}"/>
<g fill="none" stroke="{hair}" stroke-width="2.5" stroke-linecap="round"><path d="M43 58Q48 55 53 58M75 58Q80 55 85 58"/></g>
<g fill="#342A32"><ellipse cx="49" cy="67" rx="2.2" ry="2.8"/><ellipse cx="79" cy="67" rx="2.2" ry="2.8"/></g>
<path d="M64 68L61 77H66" fill="none" stroke="#91583E" stroke-opacity=".6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<g fill="#D96B72" opacity=".28"><ellipse cx="46" cy="78" rx="6" ry="3"/><ellipse cx="82" cy="78" rx="6" ry="3"/></g>
<path d="M56 85Q64 92 72 85" fill="none" stroke="#85444C" stroke-width="2.5" stroke-linecap="round"/>
{extras}
<path d="M46 103L57 117L64 110L72 117L82 103" fill="none" stroke="#FFF" stroke-opacity=".55" stroke-width="2.5" stroke-linejoin="round"/>
</g></svg>'''

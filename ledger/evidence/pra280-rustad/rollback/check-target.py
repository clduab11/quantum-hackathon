"""The rollback target must fail on pra280-rustad and pass on the rollback output.

Target: the exact pra261-schur (submission-007) member inventory.
"""
import hashlib
import sys
import zipfile

TARGET = {
    'dfthcsos/angle_k_0.kmb': '60d9dfb7a5ec6d172232f4d7081b858ce6868eea0ca2ee99ed3c99a195c3d0bb',
    'dfthcsos/angle_k_1.kmb': '4079e0a08491fc3e42df613b09fd6c8399364bdf8cc508c0de2814f7ddf75c19',
    'dfthcsos/angle_k_2.kmb': 'cacdff488e6ea968f9f60f80072ca9285036b65a98a1cd60576190960458eb1a',
    'dfthcsos/angle_k_3.kmb': 'dbe4415e56782c83b6a53045ca7325a66528ae3812a28e577e0a527d89ba77bd',
    'dfthcsos/angle_k_4.kmb': '6e0dcbe0f75a631c60e5d3affcf01179c4599abea05c053ef94d04e0a5f7d472',
    'dfthcsos/angle_k_5.kmb': '58b75e436ff504af19b40fdb23337c7c548db8f84a3bdc9710d8f8303deee41f',
    'dfthcsos/angle_k_6.kmb': '9df59056b173c4205a944c59edb4cfe5c77f0fd6003dbb34f2864910204b8d09',
    'dfthcsos/angle_k_7.kmb': '86bc88ad3aad4553f60f3eac26807acd42a949ebc48bbb2443688193f9a9b1f4',
    'dfthcsos/submission.npz': '809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5',
    'dqi.kmb': '1a1c60ae30f506ec5d05728d893f63d2e0c4952b0145af2081236bfef1e18f48',
    'invsqrt.kmb': '75e8a0e2341bb3e8f8ded1ec1d53e24437410c69e887da9daf7d49bfcc28c2dd',
}

with zipfile.ZipFile(sys.argv[1]) as archive:
    actual = {}
    for name in sorted(archive.namelist()):
        with archive.open(name) as stream:
            actual[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
wrong = sorted(n for n in set(actual) | set(TARGET) if actual.get(n) != TARGET.get(n))
if wrong:
    raise SystemExit(f'FAIL: rollback target not met; {len(wrong)} members differ: {wrong}')
print(f'PASS: all {len(TARGET)} members equal pra261-schur')

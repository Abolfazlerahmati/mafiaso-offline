@echo off
rem get-apks.cmd - put the two original 3.4.2 APKs into original\ (Windows, no bash).
rem
rem   get-apks.cmd
rem
rem Downloads the git tag "apk-parts" as a tarball (needs the curl.exe and tar.exe
rem that ship with Windows 10 1803+), reassembles part-00 + part-01 -> set.tar and
rem verifies the SHA-256 of both files.
rem
rem Less battle-tested than get-apks.sh; if anything looks wrong, compare the
rem printed hashes with docs/00-quickstart.md by hand.

setlocal
cd /d "%~dp0"

set "EXPECT_BASE=94a9beca7ae0025062bb1f5ed76541e8a7d1df41054cc491b1b9f5325d67643b"
set "EXPECT_SPLIT=e47f734399c489d92b65270a141603e80eb956fac1a086d6ec1efb2ee4b29370"
set "TAG=apk-parts"

if not exist original mkdir original
if exist original\base.apk if exist original\split_0.apk goto verify

where curl >nul 2>nul || (echo !! curl.exe not found - Windows 10 1803+ is required & exit /b 1)
where tar  >nul 2>nul || (echo !! tar.exe not found - Windows 10 1803+ is required & exit /b 1)

echo [1/4] downloading tag %TAG% ...
if exist .apk-parts rmdir /s /q .apk-parts
mkdir .apk-parts
curl -L --fail -o .apk-parts\parts.tgz "https://codeload.github.com/Abolfazlerahmati/mafiaso-offline/tar.gz/refs/tags/%TAG%" || goto error
tar -xzf .apk-parts\parts.tgz -C .apk-parts --strip-components=1 || goto error

if exist .apk-parts\base.apk goto copy
if exist .apk-parts\set.tar goto extract
if not exist .apk-parts\part-00 goto missing
if not exist .apk-parts\part-01 goto missing
echo [3/4] concatenating part-00 + part-01 ...
copy /b .apk-parts\part-00+.apk-parts\part-01 .apk-parts\set.tar >nul || goto error

:extract
tar -xf .apk-parts\set.tar -C .apk-parts || goto error

:copy
copy /y .apk-parts\base.apk original\base.apk >nul || goto error
copy /y .apk-parts\split_0.apk original\split_0.apk >nul || goto error
rmdir /s /q .apk-parts

:verify
echo [4/4] verifying hashes ...
for /f "delims=" %%h in ('certutil -hashfile original\base.apk SHA256 ^| findstr /r "^[0-9a-fA-F][0-9a-fA-F]*$"') do set "HB=%%h"
for /f "delims=" %%h in ('certutil -hashfile original\split_0.apk SHA256 ^| findstr /r "^[0-9a-fA-F][0-9a-fA-F]*$"') do set "HS=%%h"
echo    base : %HB%
echo    split: %HS%
if /i not "%HB%"=="%EXPECT_BASE%" goto badhash
if /i not "%HS%"=="%EXPECT_SPLIT%" goto badhash
echo    OK - both files match 3.4.2
echo.
echo Next: build.cmd
exit /b 0

:missing
echo !! no base.apk / set.tar / part-00 in .apk-parts - list it:
dir .apk-parts
goto error

:badhash
echo !! hash mismatch - not the 3.4.2 build. Delete original\*.apk and retry.
goto error

:error
echo.
echo get-apks failed.
exit /b 1

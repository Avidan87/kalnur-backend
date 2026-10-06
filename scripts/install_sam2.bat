@echo off
REM Install SAM 2 for KAI Food Segmentation (Windows)
REM Run this after pip install -r requirements.txt

echo 🚀 Installing SAM 2 for KAI...
echo.

REM Install SAM 2 from GitHub
echo 📦 Installing SAM 2 package...
pip install git+https://github.com/facebookresearch/segment-anything-2.git

if %errorlevel% neq 0 (
    echo ❌ SAM 2 installation failed!
    exit /b 1
)

echo ✅ SAM 2 package installed successfully!
echo.

REM Create models directory
echo 📁 Creating models directory...
if not exist "models\sam2" mkdir models\sam2

REM Download SAM 2 small checkpoint
echo ⬇️  Downloading SAM 2 small checkpoint (~180MB)...
cd models\sam2

REM Check if checkpoint already exists
if exist "sam2_hiera_small.pt" (
    echo ✅ Checkpoint already exists, skipping download
) else (
    curl -L -o sam2_hiera_small.pt https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_small.pt

    if %errorlevel% neq 0 (
        echo ❌ Checkpoint download failed!
        echo Please download manually from:
        echo https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_small.pt
        cd ..\..
        exit /b 1
    )

    echo ✅ Checkpoint downloaded successfully!
)

cd ..\..

REM Verify installation
echo.
echo 🧪 Verifying SAM 2 installation...
python -c "from sam2.build_sam import build_sam2; print('✅ SAM 2 import successful!')" 2>nul

if %errorlevel% neq 0 (
    echo ⚠️  SAM 2 import failed. Please check installation.
    exit /b 1
)

echo.
echo 🎉 SAM 2 installation complete!
echo.
echo 📚 Next steps:
echo   1. Test food segmentation: python -m kai.agents.sam_segmentation
echo   2. Run KAI with new pipeline
echo   3. Check docs\FOODSAM_MIGRATION.md for details
echo.

pause

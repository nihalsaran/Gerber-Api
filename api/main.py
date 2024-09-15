from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import os
import zipfile
from io import BytesIO
from pygerber.gerberx3.api.v2 import GerberFile, Project
import tempfile
import shutil
from PIL import Image

app = FastAPI()

# Constants
DPMM = 40

def pixels_to_mm(pixels):
    return round(pixels / DPMM)

def process_gerber_files(zip_file):
    top_layer_files = []
    bottom_layer_files = []

    for file_name in zip_file.namelist():
        if file_name.endswith('.gbr'):
            if 'Top' in file_name:
                top_layer_files.append(file_name)
            else:
                bottom_layer_files.append(file_name)

    if not top_layer_files and not bottom_layer_files:
        raise ValueError("No valid Gerber files found in the ZIP file")

    top_project = Project(
        [
            GerberFile.from_str(
                zip_file.read(file_name).decode(),
            ) for file_name in top_layer_files
        ]
    ) if top_layer_files else None

    bottom_project = Project(
        [
            GerberFile.from_str(
                zip_file.read(file_name).decode(),
            ) for file_name in bottom_layer_files
        ]
    ) if bottom_layer_files else None

    return top_project, bottom_project

@app.post("/api/convert-gerber/")
async def convert_gerber(file: UploadFile = File(...)):
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Uploaded file must be a ZIP file")

    # Create a temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Read the uploaded ZIP file
            zip_content = await file.read()
            zip_file = zipfile.ZipFile(BytesIO(zip_content))

            # Process the Gerber files
            top_project, bottom_project = process_gerber_files(zip_file)

            # Generate output file paths
            output_top = os.path.join(temp_dir, "output_top.png")
            output_bottom = os.path.join(temp_dir, "output_bottom.png")

            # Render the top and bottom layers
            if top_project:
                top_project.parse().render_raster(output_top, dpmm=DPMM)
            if bottom_project:
                bottom_project.parse().render_raster(output_bottom, dpmm=DPMM)

            # Prepare the response
            available_images = []
            total_width_mm = 0
            total_height_mm = 0
            image_count = 0

            for output_file in [output_top, output_bottom]:
                if os.path.exists(output_file):
                    with Image.open(output_file) as img:
                        width_mm = pixels_to_mm(img.width)
                        height_mm = pixels_to_mm(img.height)
                        available_images.append({
                            "name": os.path.basename(output_file),
                            "width": width_mm,
                            "height": height_mm
                        })
                        total_width_mm += width_mm
                        total_height_mm += height_mm
                        image_count += 1

            # Calculate average dimensions
            avg_width_mm = round(total_width_mm / image_count) if image_count > 0 else 0
            avg_height_mm = round(total_height_mm / image_count) if image_count > 0 else 0

            return JSONResponse(content={
                "message": "Gerber files processed successfully",
                "available_images": available_images,
                "average_dimensions": {
                    "width": avg_width_mm,
                    "height": avg_height_mm
                }
            })

        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

# Remove the image serving and listing endpoints as they won't work in a serverless environment

# Remove the cleanup function as it's not needed in a serverless environment
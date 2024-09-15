from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import os
import zipfile
from io import BytesIO
from pygerber.gerberx3.api.v2 import GerberFile, Project
import tempfile
import shutil
from PIL import Image
import math

app = FastAPI()

# Global variable to store the path of the output directory
OUTPUT_DIR = None

# Constant for dots per millimeter
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

@app.post("/convert-gerber/")
async def convert_gerber(file: UploadFile = File(...)):
    global OUTPUT_DIR
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Uploaded file must be a ZIP file")

    # Create a new output directory for this conversion
    OUTPUT_DIR = tempfile.mkdtemp()

    try:
        # Read the uploaded ZIP file
        zip_content = await file.read()
        zip_file = zipfile.ZipFile(BytesIO(zip_content))

        # Process the Gerber files
        top_project, bottom_project = process_gerber_files(zip_file)

        # Generate output file paths
        output_top = os.path.join(OUTPUT_DIR, "output_top.png")
        output_bottom = os.path.join(OUTPUT_DIR, "output_bottom.png")

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

        if os.path.exists(output_top):
            with Image.open(output_top) as img:
                width_mm = pixels_to_mm(img.width)
                height_mm = pixels_to_mm(img.height)
                available_images.append({
                    "name": "output_top.png",
                    "width": width_mm,
                    "height": height_mm
                })
                total_width_mm += width_mm
                total_height_mm += height_mm
                image_count += 1

        if os.path.exists(output_bottom):
            with Image.open(output_bottom) as img:
                width_mm = pixels_to_mm(img.width)
                height_mm = pixels_to_mm(img.height)
                available_images.append({
                    "name": "output_bottom.png",
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

@app.get("/images/{image_name}")
async def get_image(image_name: str):
    global OUTPUT_DIR
    if not OUTPUT_DIR:
        raise HTTPException(status_code=404, detail="No images available. Please convert Gerber files first.")
    
    image_path = os.path.join(OUTPUT_DIR, image_name)
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image not found")
    
    return FileResponse(image_path, media_type="image/png", filename=image_name)

@app.get("/list-images/")
async def list_images():
    global OUTPUT_DIR
    if not OUTPUT_DIR:
        return JSONResponse(content={"available_images": []})
    
    available_images = []
    total_width_mm = 0
    total_height_mm = 0
    image_count = 0

    for f in os.listdir(OUTPUT_DIR):
        if f.endswith('.png'):
            with Image.open(os.path.join(OUTPUT_DIR, f)) as img:
                width_mm = pixels_to_mm(img.width)
                height_mm = pixels_to_mm(img.height)
                available_images.append({
                    "name": f,
                    "width": width_mm,
                    "height": height_mm
                })
                total_width_mm += width_mm
                total_height_mm += height_mm
                image_count += 1

    avg_width_mm = round(total_width_mm / image_count) if image_count > 0 else 0
    avg_height_mm = round(total_height_mm / image_count) if image_count > 0 else 0

    return JSONResponse(content={
        "available_images": available_images,
        "average_dimensions": {
            "width": avg_width_mm,
            "height": avg_height_mm
        }
    })

@app.on_event("shutdown")
def cleanup():
    global OUTPUT_DIR
    if OUTPUT_DIR:
        shutil.rmtree(OUTPUT_DIR, ignore_errors=True)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
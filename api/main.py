from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
import os
import zipfile
from io import BytesIO
from pygerber.gerberx3.api.v2 import GerberFile, Project
import tempfile
from PIL import Image
import uuid
import time

app = FastAPI()

# Constant for dots per millimeter
DPMM = 40

# Temporary storage directory
TEMP_DIR = "/tmp/gerber_images"
os.makedirs(TEMP_DIR, exist_ok=True)

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

def cleanup_old_files():
    current_time = time.time()
    for filename in os.listdir(TEMP_DIR):
        file_path = os.path.join(TEMP_DIR, filename)
        if os.path.isfile(file_path):
            if os.stat(file_path).st_mtime < current_time - 3600:  # 1 hour old
                os.remove(file_path)

@app.post("/api/convert-gerber")
async def convert_gerber(file: UploadFile = File(...), background_tasks: BackgroundTasks):
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Uploaded file must be a ZIP file")

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Read the uploaded ZIP file
            zip_content = await file.read()
            zip_file = zipfile.ZipFile(BytesIO(zip_content))

            # Process the Gerber files
            top_project, bottom_project = process_gerber_files(zip_file)

            # Generate output file paths
            unique_id = str(uuid.uuid4())
            output_top = os.path.join(TEMP_DIR, f"output_top_{unique_id}.png")
            output_bottom = os.path.join(TEMP_DIR, f"output_bottom_{unique_id}.png")

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
                            "height": height_mm,
                            "url": f"/api/images/{os.path.basename(output_file)}"
                        })
                        total_width_mm += width_mm
                        total_height_mm += height_mm
                        image_count += 1

            # Calculate average dimensions
            avg_width_mm = round(total_width_mm / image_count) if image_count > 0 else 0
            avg_height_mm = round(total_height_mm / image_count) if image_count > 0 else 0

            # Schedule cleanup task
            background_tasks.add_task(cleanup_old_files)

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

@app.get("/api/images/{image_name}")
async def get_image(image_name: str, background_tasks: BackgroundTasks):
    image_path = os.path.join(TEMP_DIR, image_name)
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Schedule cleanup task
    background_tasks.add_task(cleanup_old_files)
    
    return FileResponse(image_path, media_type="image/png", filename=image_name)

@app.get("/api/list-images")
async def list_images(background_tasks: BackgroundTasks):
    images = []
    for filename in os.listdir(TEMP_DIR):
        if filename.endswith('.png'):
            images.append({
                "name": filename,
                "url": f"/api/images/{filename}"
            })
    
    # Schedule cleanup task
    background_tasks.add_task(cleanup_old_files)
    
    return JSONResponse(content={"available_images": images})

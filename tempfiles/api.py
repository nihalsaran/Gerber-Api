from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import os
import zipfile
from io import BytesIO
from pathlib import Path
from pygerber.gerberx3.api.v2 import FileTypeEnum, GerberFile, Project
import tempfile
import shutil

app = FastAPI()

# Global variable to store the path of the output directory
OUTPUT_DIR = None

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
            top_project.parse().render_raster(output_top, dpmm=40)
        if bottom_project:
            bottom_project.parse().render_raster(output_bottom, dpmm=40)

        # Prepare the response
        available_images = []
        if os.path.exists(output_top):
            available_images.append("output_top.png")
        if os.path.exists(output_bottom):
            available_images.append("output_bottom.png")

        return JSONResponse(content={
            "message": "Gerber files processed successfully",
            "available_images": available_images
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
    
    available_images = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.png')]
    return JSONResponse(content={"available_images": available_images})

@app.on_event("shutdown")
def cleanup():
    global OUTPUT_DIR
    if OUTPUT_DIR:
        shutil.rmtree(OUTPUT_DIR, ignore_errors=True)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
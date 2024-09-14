from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import zipfile
from io import BytesIO
from pathlib import Path
from pygerber.gerberx3.api.v2 import FileTypeEnum, GerberFile, Project
import tempfile
import shutil

app = FastAPI()

# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")

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

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

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

# Create a templates directory and add the index.html file
os.makedirs("templates", exist_ok=True)
with open("templates/index.html", "w") as f:
    f.write("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gerber File Converter</title>
    <script src="https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        h1 { color: #333; }
        #result { margin-top: 20px; font-weight: bold; }
        #images { margin-top: 20px; }
        img { max-width: 100%; margin-top: 10px; border: 1px solid #ddd; }
    </style>
</head>
<body>
    <h1>Gerber File Converter</h1>
    <input type="file" id="gerberFile" accept=".zip">
    <button onclick="convertGerber()">Convert</button>
    <div id="result"></div>
    <div id="images"></div>

    <script>
        async function convertGerber() {
            const fileInput = document.getElementById('gerberFile');
            const file = fileInput.files[0];
            if (!file) {
                alert('Please select a file');
                return;
            }

            const formData = new FormData();
            formData.append('file', file);

            try {
                const response = await axios.post('/convert-gerber/', formData, {
                    headers: {
                        'Content-Type': 'multipart/form-data'
                    }
                });

                document.getElementById('result').innerHTML = response.data.message;
                const imagesDiv = document.getElementById('images');
                imagesDiv.innerHTML = '';
                response.data.available_images.forEach(imageName => {
                    const img = document.createElement('img');
                    img.src = `/images/${imageName}`;
                    img.alt = imageName;
                    imagesDiv.appendChild(img);
                });
            } catch (error) {
                document.getElementById('result').innerHTML = `Error: ${error.response.data.detail}`;
            }
        }
    </script>
</body>
</html>
    """)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
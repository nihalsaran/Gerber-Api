from flask import Flask, request, jsonify
import zipfile
from io import BytesIO
from pygerber.gerberx3.api.v2 import GerberFile, Project

app = Flask(__name__)

@app.route('/process-gerber', methods=['POST'])
def process_gerber():
    uploaded_file = request.files['zip_file']
    top_layer_files = []
    bottom_layer_files = []

    # Open the ZIP file
    with zipfile.ZipFile(uploaded_file, 'r') as zip_file:
        for file_name in zip_file.namelist():
            if file_name.endswith('.gbr'):
                if 'Top' in file_name:
                    top_layer_files.append(file_name)
                else:
                    bottom_layer_files.append(file_name)

        top_project = Project(
            [GerberFile.from_str(zip_file.read(file_name).decode()) for file_name in top_layer_files]
        )

        bottom_project = Project(
            [GerberFile.from_str(zip_file.read(file_name).decode()) for file_name in bottom_layer_files]
        )

    top_image = top_project.parse().render_raster("output_top.png", dpmm=40)
    bottom_image = bottom_project.parse().render_raster("output_bottom.png", dpmm=40)

    return jsonify({'top_image': 'output_top.png', 'bottom_image': 'output_bottom.png'})

if __name__ == '__main__':
    app.run(debug=True)

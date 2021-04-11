  
from flask_wtf import FlaskForm
import wtforms as f
from wtforms import Form, BooleanField
from wtforms.validators import DataRequired, Length, ValidationError

class DownloadForm(FlaskForm):
    file_cid = f.StringField('File CID', validators=[DataRequired(), Length(1, 64)])
    display = ['file_cid']

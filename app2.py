import dash
from dash import dcc  # dash core components
from dash import html # dash html components 
from dash.dependencies import Input, Output

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
server = app.server

app.layout = html.Div(
    [
    html.H6("Modifique el valor en la caja de texto para ver el funcionamiento de los callbacks"),
    html.Div(["Input: ",
              dcc.Input(id='my-input', value='valor inicial', type='text')]),
    html.Br(),
    html.Div(id='my-output'),
    ]
)


@app.callback(
    Output(component_id='my-output', component_property='children'),
    [Input(component_id='my-input', component_property='value')]
)
def update_output_div(input_value):
    return 'Output: {}'.format(input_value)


if __name__ == '__main__':
    app.run_server(debug=True)

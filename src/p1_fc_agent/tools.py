from pydantic import BaseModel


class WeatherQuery(BaseModel):
    city: str
    unit: str = "celsius"


class DateRange(BaseModel):
    start: str
    end: str


class TripQuery(BaseModel):
    origin: str
    destination: str
    date_range: DateRange
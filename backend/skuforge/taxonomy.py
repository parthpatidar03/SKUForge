"""Category-aware attribute templates (IDEA/UNSPSC-inspired, electrical-first).

The classifier picks one; the extractor targets exactly these attributes.
GENERIC is the fallback for unknown categories.
"""

TEMPLATES: dict[str, dict] = {
    "circuit_breaker": {
        "label": "Circuit Breaker",
        "attributes": [
            "amperage_rating", "voltage_rating", "number_of_poles",
            "interrupt_rating_ka", "breaker_type", "mounting_type",
            "wire_size_range", "frame_type", "trip_type", "width_inches",
        ],
    },
    "contactor": {
        "label": "Contactor / Motor Starter",
        "attributes": [
            "coil_voltage", "full_load_amps", "number_of_poles", "nema_size",
            "horsepower_rating", "auxiliary_contacts", "mounting_type", "enclosure_type",
        ],
    },
    "switch": {
        "label": "Switch (Wiring Device)",
        "attributes": [
            "amperage_rating", "voltage_rating", "switch_type", "number_of_gangs",
            "color", "wiring_type", "mounting_type", "material",
        ],
    },
    "receptacle": {
        "label": "Receptacle / Outlet",
        "attributes": [
            "amperage_rating", "voltage_rating", "nema_configuration",
            "receptacle_type", "color", "gfci_protection", "tamper_resistant",
            "weather_resistant", "mounting_type",
        ],
    },
    "luminaire": {
        "label": "Lighting / Luminaire",
        "attributes": [
            "wattage", "lumens", "color_temperature_k", "voltage_rating",
            "lamp_type", "dimmable", "mounting_type", "ip_rating", "cri",
        ],
    },
    "wire_cable": {
        "label": "Wire & Cable",
        "attributes": [
            "conductor_gauge_awg", "number_of_conductors", "voltage_rating",
            "insulation_type", "jacket_material", "temperature_rating_c",
            "length_ft", "conductor_material", "shielded",
        ],
    },
    "motor": {
        "label": "Electric Motor",
        "attributes": [
            "horsepower", "rpm", "voltage_rating", "phase", "frame_size",
            "enclosure_type", "frequency_hz", "full_load_amps", "service_factor",
            "shaft_diameter",
        ],
    },
    "transformer": {
        "label": "Transformer",
        "attributes": [
            "kva_rating", "primary_voltage", "secondary_voltage", "phase",
            "frequency_hz", "mounting_type", "enclosure_type", "temperature_rise_c",
        ],
    },
    "relay": {
        "label": "Relay / Timer",
        "attributes": [
            "coil_voltage", "contact_rating_amps", "contact_configuration",
            "relay_type", "mounting_type", "number_of_poles", "socket_type",
        ],
    },
    "conduit_fitting": {
        "label": "Conduit & Fittings",
        "attributes": [
            "trade_size_inches", "material", "fitting_type", "connection_type",
            "conduit_type", "temperature_rating_c", "ul_listed",
        ],
    },
    "plumbing_valve": {
        "label": "Plumbing Valve",  # cross-vertical proof SKU
        "attributes": [
            "valve_type", "connection_size_inches", "connection_type", "material",
            "max_pressure_psi", "max_temperature_f", "handle_type", "lead_free",
        ],
    },
    "generic": {
        "label": "General Industrial Product",
        "attributes": [
            "material", "color", "weight", "dimensions", "voltage_rating",
            "operating_temperature", "standards_compliance",
        ],
    },
}

# Attributes every record gets regardless of category.
UNIVERSAL_ATTRIBUTES = ["upc_gtin", "country_of_origin", "warranty", "weight_lbs"]


def get_template(category: str) -> dict:
    return TEMPLATES.get(category, TEMPLATES["generic"])


def category_ids() -> list[str]:
    return list(TEMPLATES.keys())

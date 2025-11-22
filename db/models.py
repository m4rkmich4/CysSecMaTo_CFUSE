from typing import List, Optional, Literal
from uuid import UUID
from pydantic import BaseModel, Field, EmailStr, AnyHttpUrl
from datetime import datetime

# ------------------------------------------------------------------------------
# Represents an external or internal link in the metadata
# ------------------------------------------------------------------------------
class Link(BaseModel):
    """
    Represents a hyperlink in the metadata section.

    :ivar href: Target URL (must start with http or https)
    :ivar rel: Relationship type (e.g., 'reference')
    """
    href: AnyHttpUrl
    rel: str


# ------------------------------------------------------------------------------
# Represents an organization or person in the document
# ------------------------------------------------------------------------------
class Party(BaseModel):
    """
    Represents an involved party (organization or person).

    :ivar uuid: Unique UUID
    :ivar type: Party type ('organization' or 'person')
    :ivar name: Display name
    :ivar email_addresses: List of associated email addresses
    :ivar remarks: Optional free-text remarks
    """
    uuid: UUID
    type: Literal["organization", "person"]
    name: str
    email_addresses: List[EmailStr] = Field(default_factory=list, alias="email-addresses")
    remarks: Optional[str] = None


# ------------------------------------------------------------------------------
# Associates roles with party UUIDs (e.g., author, point of contact)
# ------------------------------------------------------------------------------
class ResponsibleParty(BaseModel):
    """
    Associates roles with one or more parties.

    :ivar role_id: Role identifier
    :ivar party_uuids: List of referenced party UUIDs
    """
    role_id: str = Field(alias="role-id")
    party_uuids: List[UUID] = Field(alias="party-uuids")


# ------------------------------------------------------------------------------
# Contains metadata information for the catalog
# ------------------------------------------------------------------------------
class Metadata(BaseModel):
    """
    Top-level information about the document.

    :ivar title: Catalog title
    :ivar published: Publication datetime
    :ivar last_modified: Last modification datetime (ISO timestamp)
    :ivar version: Catalog version
    :ivar oscal_version: OSCAL specification version used
    :ivar links: References to external or internal sources
    :ivar parties: List of involved parties
    :ivar responsible_parties: Assignment of roles to parties
    """
    title: str
    published: datetime
    last_modified: datetime = Field(alias="last-modified")
    version: str
    oscal_version: str = Field(alias="oscal-version")
    links: Optional[List[Link]] = Field(default_factory=list)
    parties: Optional[List[Party]] = Field(default_factory=list)
    responsible_parties: Optional[List[ResponsibleParty]] = Field(default_factory=list, alias="responsible-parties")


# ------------------------------------------------------------------------------
# Property = arbitrary key-value pair for categorization
# ------------------------------------------------------------------------------
class Property(BaseModel):
    """
    Arbitrary property (e.g., 'criticality', 'chapter').

    :ivar name: Property key
    :ivar value: Property value
    """
    name: str
    value: str


# ------------------------------------------------------------------------------
# Part = structured text block within a control (e.g., description, guidance)
# ------------------------------------------------------------------------------
class Part(BaseModel):
    """
    Text segment within a control.

    :ivar name: Type (e.g., 'description', 'guidance')
    :ivar prose: Associated narrative text
    """
    name: str
    prose: str


# ------------------------------------------------------------------------------
# Control = individual security requirement
# ------------------------------------------------------------------------------
class Control(BaseModel):
    """
    Represents a security control with metadata and optional sub-controls.

    :ivar id: Control ID (must be unique)
    :ivar title: Human-readable control title
    :ivar class_: Classification (parent, child, stand_alone)
    :ivar props: Arbitrary properties
    :ivar parts: Structured text parts
    :ivar controls: Sub-controls (nested recursively)
    """
    id: str
    title: str
    class_: Optional[str] = Field(default="stand_alone", alias="class")
    props: Optional[List[Property]] = Field(default_factory=list)
    parts: Optional[List[Part]] = Field(default_factory=list)
    controls: Optional[List["Control"]] = Field(default_factory=list)


# ------------------------------------------------------------------------------
# Group = logical grouping of controls (e.g., family, chapter)
# ------------------------------------------------------------------------------
class Group(BaseModel):
    """
    Collection of thematically related controls.

    :ivar id: Unique group ID
    :ivar class_: Classification type (usually 'family')
    :ivar title: Group title (e.g., 'Access Control')
    :ivar props: Optional meta-properties of the group
    :ivar controls: List of contained controls
    """
    id: str
    class_: str = Field(alias="class")
    title: str
    props: Optional[List[Property]] = Field(default_factory=list)
    controls: List[Control]


# ------------------------------------------------------------------------------
# Catalog = entry point, top-level object for everything
# ------------------------------------------------------------------------------
class Catalog(BaseModel):
    """
    OSCAL Catalog (root element).

    :ivar uuid: Unique catalog identifier
    :ivar metadata: Metadata block
    :ivar groups: Group structure containing all controls
    """
    uuid: UUID
    metadata: Metadata
    groups: List[Group]


# ------------------------------------------------------------------------------
# Helper function to validate and load OSCAL catalog data
# ------------------------------------------------------------------------------

def load_catalog_from_dict(data: dict) -> Catalog:
    """
    Loads an OSCAL-formatted dictionary into a valid Catalog model.

    :param data: JSON-like dictionary with 'catalog' key
    :return: Valid Catalog model
    """
    return Catalog(**data["catalog"])

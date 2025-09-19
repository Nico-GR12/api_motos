from fastapi import FastAPI, Depends, Query, HTTPException
from sqlmodel import Field, Session, create_engine, select, SQLModel, Relationship
from typing import Annotated, Optional, List
from datetime import datetime


url_connection = 'mysql+pymysql://root:@localhost:3306/api_moto'
engine = create_engine(url_connection)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

SessionDep = Annotated[Session, Depends(get_session)]


class MarcaBase(SQLModel):
    nombre: str = Field(index=True, max_length=50)
    pais_origen: str = Field(max_length=30)
    anio_fundacion: int = Field(ge=1800, le=datetime.now().year)

class Marca(MarcaBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    motos: List["Moto"] = Relationship(back_populates="marca")

class MotoBase(SQLModel):
    modelo: str = Field(index=True, max_length=50)
    cilindrada: int = Field(ge=50, le=3000)
    potencia: int = Field(ge=5, le=500)
    precio: float = Field(ge=0)
    anio: int = Field(ge=1900, le=datetime.now().year + 1)

class Moto(MotoBase, table=True):
    id_moto: Optional[int] = Field(default=None, primary_key=True)
    marca_id: Optional[int] = Field(default=None, foreign_key="marca.id")
    marca: Optional[Marca] = Relationship(back_populates="motos")
    especificaciones: Optional["Especificacion"] = Relationship(
        back_populates="moto", 
        sa_relationship_kwargs={"uselist": False}
    )

class EspecificacionBase(SQLModel):
    tipo_motor: str = Field(max_length=30)
    refrigeracion: str = Field(max_length=20)
    transmision: int 
    capacidad_tanque: float = Field(ge=0)

class Especificacion(EspecificacionBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    id_moto: Optional[int] = Field(
        default=None, 
        foreign_key="moto.id_moto",
        unique=True
    )
    moto: Optional[Moto] = Relationship(back_populates="especificaciones")



class MarcaCreate(MarcaBase):
    pass

class MarcaPublic(MarcaBase):
    id: int

class MotoCreate(MotoBase):
    marca_id: int

class MotoPublic(MotoBase):
    id_moto: int
    marca_id: int

class MotoConMarca(MotoPublic):
    marca: Optional[MarcaPublic] = None

class MotoConEspecificaciones(MotoPublic):
    especificaciones: Optional["EspecificacionPublic"] = None
    marca: Optional[MarcaPublic] = None

class EspecificacionCreate(EspecificacionBase):
    id_moto: int

class EspecificacionPublic(EspecificacionBase):
    id: int
    id_moto: int

class EspecificacionConMoto(EspecificacionPublic):
    moto: Optional[MotoPublic] = None


app = FastAPI(
    title="API de Motos", 
    version="1.0.0",
    description="API para gestión de motos, marcas y especificaciones técnicas"
)


@app.post("/marcas/", response_model=MarcaPublic)
def crear_marca(marca: MarcaCreate, session: SessionDep):
    db_marca = Marca.model_validate(marca)
    session.add(db_marca)
    session.commit()
    session.refresh(db_marca)
    return db_marca


@app.post("/motos/", response_model=MotoPublic)
def crear_moto(moto: MotoCreate, session: SessionDep):
    marca = session.get(Marca, moto.marca_id)
    if not marca:
        raise HTTPException(
            status_code=404, 
            detail=f"Marca con ID {moto.marca_id} no encontrada"
        )
    
    db_moto = Moto.model_validate(moto)
    session.add(db_moto)
    session.commit()
    session.refresh(db_moto)
    return db_moto

@app.get("/motos/", response_model=List[MotoPublic])
def listar_motos(
    session: SessionDep,
    skip: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
    marca_id: Optional[int] = None,
    tipo: Optional[str] = None
):
    query = select(Moto)
    
    if marca_id:
        query = query.where(Moto.marca_id == marca_id)
    if tipo:
        query = query.where(Moto.tipo == tipo)
    
    motos = session.exec(query.offset(skip).limit(limit)).all()
    return motos

@app.get("/motos/{moto_id}", response_model=MotoConMarca)
def obtener_moto(moto_id: int, session: SessionDep):
    moto = session.get(Moto, moto_id)
    if not moto:
        raise HTTPException(status_code=404, detail="Moto no encontrada")
    return moto

@app.patch("/motos/{moto_id}", response_model=MotoPublic)
def actualizar_moto(moto_id: int, moto_update: MotoBase, session: SessionDep):
    moto_db = session.get(Moto, moto_id)
    if not moto_db:
        raise HTTPException(status_code=404, detail="Moto no encontrada")
    
    moto_data = moto_update.model_dump(exclude_unset=True)
    for key, value in moto_data.items():
        setattr(moto_db, key, value)
    
    session.add(moto_db)
    session.commit()
    session.refresh(moto_db)
    return moto_db

@app.delete("/motos/{moto_id}")
def eliminar_moto(moto_id: int, session: SessionDep):
    moto = session.get(Moto, moto_id)
    if not moto:
        raise HTTPException(status_code=404, detail="Moto no encontrada")
    
    # Verificar si tiene especificaciones asociadas
    especificaciones = session.exec(
        select(Especificacion).where(Especificacion.moto_id == moto_id)
    ).first()
    
    if especificaciones:
        # Eliminar primero las especificaciones
        session.delete(especificaciones)
    
    session.delete(moto)
    session.commit()
    return {"ok": True}

@app.post("/especificaciones/", response_model=EspecificacionPublic)
def crear_especificacion(espec: EspecificacionCreate, session: SessionDep):
    moto = session.get(Moto, espec.id_moto)
    if not moto:
        raise HTTPException(
            status_code=404, 
            detail=f"Moto con ID {espec.id_moto} no encontrada"
        )
    
    existing_espec = session.exec(
        select(Especificacion).where(Especificacion.id_moto == espec.id_moto)
    ).first()
    
    if existing_espec:
        raise HTTPException(
            status_code=400, 
            detail=f"La moto {espec.id_moto} ya tiene especificaciones"
        )
    
    db_espec = Especificacion.model_validate(espec)
    session.add(db_espec)
    session.commit()
    session.refresh(db_espec)
    return db_espec















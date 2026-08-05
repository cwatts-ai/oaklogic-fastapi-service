from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database import Base, SessionLocal, engine
from src.models.product import (
    Category,
    CategoryCreate,
    CategorySchema,
    Product,
    ProductCreate,
    ProductSchema,
)
from src.repositories.category_repository import CategoryRepository
from src.repositories.product_repository import (
    ProductRepository,
    ProductUpdateRepository,
)

app = FastAPI()

# Drop & create tables on startup
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)


def get_db():
    """Provide a database session for each request.

    Yields:
        Session: An active SQLAlchemy database session.

    Ensures:
        The database session is closed after the request is completed.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def root():
    """Return a welcome message.

    Returns:
        A simple greeting indicating that the API is running.
    """
    return {"message": "Hello World"}


@app.get("/hello/{name}")
def say_hello(name: str):
    """Return a personalized greeting.

    Args:
        name: The name to include in the greeting.

    Returns:
        A greeting message containing the provided name.
    """
    return {"message": f"Hello, {name}!"}


@app.get("/db-check")
def db_check(db: Session = Depends(get_db)):
    """Verify the database connection.

    Args:
        db: The active database session.

    Returns:
        The current number of products stored in the database.
    """
    count = db.query(Product).count()
    return {"product_count": count}


# ==========================================
# CATEGORY ENDPOINTS
# ==========================================


@app.post(
    "/categories",
    response_model=CategorySchema,
    status_code=status.HTTP_201_CREATED,
)
def create_category(category_data: CategoryCreate, db: Session = Depends(get_db)):
    """Create a new category.

    Args:
        category_data: The category information to create.
        db: The active database session.

    Returns:
        The newly created category.

    Raises:
        HTTPException: If a category with the same name already exists.
    """
    repo = CategoryRepository(db)
    try:
        return repo.create_category(category_data)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Category '{category_data.name}' already exists",
        )


@app.get("/categories", response_model=list[CategorySchema])
def get_categories(db: Session = Depends(get_db)):
    """Retrieve all categories.

    Args:
        db: The active database session.

    Returns:
        A list of all categories.
    """
    repo = CategoryRepository(db)
    return repo.get_all_categories()


@app.get("/categories/{category_id}", response_model=CategorySchema)
def get_category_by_id(category_id: int, db: Session = Depends(get_db)):
    """Retrieve a category by its ID.

    Args:
        category_id: The ID of the category.
        db: The active database session.

    Returns:
        The matching category.

    Raises:
        HTTPException: If the category does not exist.
    """
    repo = CategoryRepository(db)
    category = repo.get_category_by_id(category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with ID {category_id} was not found",
        )
    return category


# ==========================================
# PRODUCT ENDPOINTS
# ==========================================

@app.post("/products", response_model=ProductSchema, status_code=status.HTTP_201_CREATED)
def create_product(product_data: ProductCreate, db: Session = Depends(get_db)):
    """Create a new product.

    Validates that the referenced category exists before creating the product.

    Args:
        product_data: The product information.
        db: The active database session.

    Returns:
        The newly created product.

    Raises:
        HTTPException: If the category does not exist or the product already exists.
    """
    # 1. Validate that the referenced category exists BEFORE inserting
    if product_data.category_id is not None:
        cat_repo = CategoryRepository(db)
        category = cat_repo.get_category_by_id(product_data.category_id)

        if not category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category with ID {product_data.category_id} does not exist",
            )

    repository = ProductRepository(db)
    existing_product = repository.get_product_by_exact_name(product_data.name)

    if existing_product is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Product '{product_data.name}' already exists",
    )

    try:
        new_product = repository.create_new_product(product_data)
        db.expire_all()
        return new_product
    except IntegrityError as e:
        db.rollback()
        err_str = str(e.orig).lower() if hasattr(e, "orig") else ""
        if "foreign key" in err_str or "foreignkey" in err_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category with ID {product_data.category_id} does not exist",
            )
        raise HTTPException(
            status_code=status.HTTP_400_CONFLICT,
            detail=f"Product '{product_data.name}' already exists",
        )


@app.get("/products", response_model=list[ProductSchema])
def get_products(db: Session = Depends(get_db)):
    """Retrieve all products.

    Args:
        db: The active database session.

    Returns:
        A list of all products.
    """
    repository = ProductRepository(db)
    return repository.get_all_products()


@app.get("/products/search/{identifier}", response_model=ProductSchema)
def get_product(identifier: str, db: Session = Depends(get_db)):
    """Retrieve a product by its ID or name.

    If the identifier is numeric, it is treated as a product ID.
    Otherwise, it is treated as a product name.

    Args:
        identifier: The product ID or name.
        db: The active database session.

    Returns:
        The matching product.

    Raises:
        HTTPException: If no matching product is found.
    """
    repository = ProductRepository(db)

    if identifier.isdigit():
        product = repository.get_product_by_id(int(identifier))
    else:
        product = repository.get_product_by_name(identifier)

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product '{identifier}' was not found",
        )

    return product


@app.get("/products/filter/", response_model=list[ProductSchema])
def filter_products(
    name: str | None = None,
    unit: str | None = None,
    cost_per_unit: float | None = None,
    price_per_unit: float | None = None,
    quantity_in_stock: float | None = None,
    db: Session = Depends(get_db),
):
    """Filter products using one or more optional criteria.

    Args:
        name: Product name filter.
        unit: Unit of measurement filter.
        cost_per_unit: Cost per unit filter.
        price_per_unit: Price per unit filter.
        quantity_in_stock: Quantity in stock filter.
        db: The active database session.

    Returns:
        A list of products matching the specified filters.
    """

    repository = ProductRepository(db)

    products = repository.search_products(
        name=name,
        unit=unit,
        cost_per_unit=cost_per_unit,
        price_per_unit=price_per_unit,
        quantity_in_stock=quantity_in_stock,
    )

    if not products:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No products found matching the specified filters."
        )

    return products


@app.delete("/products/{product_id}")
def delete_product_by_id(product_id: int, db: Session = Depends(get_db)):
    """Delete a product by its ID.

    Args:
        product_id: The ID of the product to delete.
        db: The active database session.

    Returns:
        A 204 No Content response.

    Raises:
        HTTPException: If the product does not exist.
    """
    repository = ProductRepository(db)
    if not repository.delete_product_by_id(product_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} was not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/products/name/{product_name}")
def delete_product_by_name(product_name: str, db: Session = Depends(get_db)):
    repository = ProductRepository(db)
    cleaned_name = product_name.strip()

    
    exact_product = repository.get_product_by_exact_name(cleaned_name)
    """Delete a product by its name.

    Args:
        product_name: The name of the product to delete.
        db: The active database session.

    Returns:
        A 204 No Content response.

    Raises:
        HTTPException: If the product does not exist.
    """

    if exact_product is not None:
        repository.delete_product_by_name(cleaned_name)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # No exact match, so check whether the input partially matches products
    matches = repository.search_products_by_name(cleaned_name)

    if len(matches) > 1:
        matching_names = [product.name for product in matches]

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Multiple products match '{cleaned_name}': "
                f"{', '.join(matching_names)}. "
                "Enter the full product name to delete."
            ),
        )

    if len(matches) == 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{cleaned_name}' partially matches '{matches[0].name}'. "
                "Enter the full product name to delete."
            ),
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Product with name '{cleaned_name}' was not found",
    )


@app.put("/products/{identifier}", response_model=ProductSchema)
def update_product(
    identifier: str,
    product_data: ProductCreate | ProductSchema,
    db: Session = Depends(get_db),
):
    """Update an existing product by its ID or name.

    If the identifier is numeric, it is treated as a product ID.
    Otherwise, it is treated as a product name.

    Args:
        identifier: The product ID or name.
        product_data: The updated product information.
        db: The active database session.

    Returns:
        The updated product.

    Raises:
        HTTPException: If the product ID is invalid or the product is not found.
    """
    repository = ProductUpdateRepository()

    if identifier.isdigit():
        product_id = int(identifier)
        if product_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Product ID must be greater than 0.",
            )
        product = repository.update_product(
            db=db,
            product_data=product_data,
            product_id=product_id,
        )
    else:
        product = repository.update_product(
            db=db,
            product_data=product_data,
            product_name=identifier,
        )

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return product

@app.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, db: Session = Depends(get_db)):
    """Delete a category by its ID.

    Only allowed if the category has no products assigned to it.

    Args:
        category_id: The ID of the category to delete.
        db: The active database session.

    Returns:
        A 204 No Content response.

    Raises:
        HTTPException: If the category does not exist, or if it still has products.
    """
    repo = CategoryRepository(db)
    category = repo.get_category_by_id(category_id)

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with ID {category_id} was not found",
        )

    if len(category.products) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Category '{category.name}' has {len(category.products)} "
                "product(s) assigned to it and cannot be deleted."
            ),
        )

    repo.delete_category_by_id(category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
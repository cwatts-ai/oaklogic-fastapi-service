# Garden Center Product API Technical Specification

## Overview

This FastAPI application allows a garden center to manage products and organize them into categories.

The application uses:

* FastAPI for routes and HTTP responses.
* Pydantic for request and response validation.
* SQLAlchemy for database models and database operations.
* PostgreSQL as the main persistent database.
* Repository classes to separate database logic from route logic.
* FastAPI dependency injection to provide one database session per request.

During development and testing, the application falls back to an in-memory SQLite database when a `DATABASE_URL` environment variable is not provided.

The Day 3 table-management strategy remains in place:

```python
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
```

This means the tables are dropped and recreated whenever the application starts.

---

# Day 4: Create and Read Products

## Purpose

Day 4 adds the ability to:

* Create and persist a product.
* Retrieve all products.
* Retrieve one product by its ID or name.
* Return a clear error when a product is not found.
* Control response data using Pydantic response models.

---

## Endpoint: Create Product

**Method:** `POST`

**Path:** `/products`

## Purpose

Creates a new product and saves it in the database.

Because the application now includes categories, the product must reference an existing category.

## Request Body

```json
{
  "name": "Rose Bush",
  "unit": "each",
  "cost_per_unit": 5.99,
  "price_per_unit": 12.99,
  "quantity_in_stock": 20,
  "category_id": 1
}
```

The `id` field may technically be included because the route currently accepts `ProductSchema`, but the repository does not use the supplied ID. PostgreSQL or SQLite generates the product ID automatically.

## Successful Response

**Status Code:**

```text
201 Created
```

**Response Body:**

```json
{
  "id": 1,
  "name": "Rose Bush",
  "unit": "each",
  "cost_per_unit": 5.99,
  "price_per_unit": 12.99,
  "quantity_in_stock": 20,
  "category_id": 1
}
```

## Failure: Invalid Category

If `category_id` does not match an existing category, the route rejects the request before attempting the product insert.

**Status Code:**

```text
400 Bad Request
```

**Response Body:**

```json
{
  "detail": "Category with ID 99 does not exist"
}
```

## Failure: Duplicate Product Name

The SQLAlchemy `Product` model requires product names to be unique.

If a product with the same name already exists, the database raises an `IntegrityError`. The route rolls back the database session and converts the error into an HTTP response.

**Status Code:**

```text
409 Conflict
```

**Response Body:**

```json
{
  "detail": "Product 'Rose Bush' already exists"
}
```

## Validation

Pydantic validates the request before the route function runs.

The current `ProductSchema` requires:

* `name` to be a string.
* `unit` to be a string.
* `cost_per_unit` to be greater than `0`.
* `price_per_unit` to be greater than `0`.
* `quantity_in_stock` to be greater than or equal to `0`.
* `category_id` to be an integer or `null`.

If Pydantic validation fails, FastAPI automatically returns:

```text
422 Unprocessable Entity
```

Example response:

```json
{
  "detail": [
    {
      "type": "greater_than",
      "loc": [
        "body",
        "price_per_unit"
      ],
      "msg": "Input should be greater than 0",
      "input": -5,
      "ctx": {
        "gt": 0
      }
    }
  ]
}
```

---

## Endpoint: Get All Products

**Method:** `GET`

**Path:** `/products`

## Purpose

Returns every product currently stored in the database.

## Request Body

None.

## Successful Response

**Status Code:**

```text
200 OK
```

**Response Body:**

```json
[
  {
    "id": 1,
    "name": "Rose Bush",
    "unit": "each",
    "cost_per_unit": 5.99,
    "price_per_unit": 12.99,
    "quantity_in_stock": 20,
    "category_id": 1
  }
]
```

If no products exist, the endpoint returns an empty list:

```json
[]
```

The endpoint uses:

```python
response_model=list[ProductSchema]
```

---

## Endpoint: Get One Product

**Method:** `GET`

**Path:** `/products/search/{identifier}`

## Purpose

Returns one product by either its ID or its name.

The route examines the path parameter:

* If the identifier contains only digits, it is treated as a product ID.
* Otherwise, it is treated as a product name.

## Example Requests

```text
GET /products/search/1
```

```text
GET /products/search/Rose%20Bush
```

## Successful Response

**Status Code:**

```text
200 OK
```

**Response Body:**

```json
{
  "id": 1,
  "name": "Rose Bush",
  "unit": "each",
  "cost_per_unit": 5.99,
  "price_per_unit": 12.99,
  "quantity_in_stock": 20,
  "category_id": 1
}
```

## Failure: Product Not Found

If no product matches the supplied ID or name:

**Status Code:**

```text
404 Not Found
```

**Example Response:**

```json
{
  "detail": "Product '999' was not found"
}
```

For a name:

```json
{
  "detail": "Product 'Unknown Plant' was not found"
}
```

---

## Additional Endpoint: Filter Products

**Method:** `GET`

**Path:** `/products/filter/`

## Purpose

Returns products that match one or more optional query parameters.

## Query Parameters

The endpoint supports:

* `name`
* `unit`
* `cost_per_unit`
* `price_per_unit`
* `quantity_in_stock`

All parameters are optional.

## Example Requests

```text
GET /products/filter/?name=rose
```

```text
GET /products/filter/?unit=each
```

```text
GET /products/filter/?name=rose&unit=each
```

```text
GET /products/filter/?price_per_unit=12.99
```

## Matching Behavior

* Product names use a case-insensitive partial match.
* Units use a case-insensitive match.
* Numeric values require exact matches.

For example:

```text
GET /products/filter/?name=rose
```

may match:

* `Rose Bush`
* `Mini Rose Plant`
* `Rosemary Rose Blend`

## Successful Response

**Status Code:**

```text
200 OK
```

**Response Body:**

```json
[
  {
    "id": 1,
    "name": "Rose Bush",
    "unit": "each",
    "cost_per_unit": 5.99,
    "price_per_unit": 12.99,
    "quantity_in_stock": 20,
    "category_id": 1
  }
]
```

If no products match, the endpoint returns:

```json
[]
```

---

# Day 5: Update, Delete, Validation, and Error Handling

## Purpose

Day 5 completes the main CRUD operations by adding:

* Full product updates.
* Product deletion by ID.
* Product deletion by name.
* Clear `404 Not Found` responses.
* Clear `400 Bad Request` responses.
* Pydantic validation for invalid numeric values.

---

## Endpoint: Update Product

**Method:** `PUT`

**Path:** `/products/{identifier}`

## Purpose

Replaces the editable data for an existing product.

The identifier may be:

* A numeric product ID.
* A product name.

## Update Type

This is a full update rather than a partial update.

The client must provide all required product fields.

## Request Body

```json
{
  "name": "Premium Rose Bush",
  "unit": "each",
  "cost_per_unit": 6.99,
  "price_per_unit": 14.99,
  "quantity_in_stock": 15,
  "category_id": 1
}
```

## Fields Updated

The repository currently updates:

* `name`
* `unit`
* `cost_per_unit`
* `price_per_unit`
* `quantity_in_stock`

The repository does not currently update:

* `id`
* `category_id`

Although `category_id` appears in the request schema, changing it in an update request does not change the product's stored category.

## Example Requests

Update by ID:

```text
PUT /products/1
```

Update by name:

```text
PUT /products/Rose%20Bush
```

## Successful Response

**Status Code:**

```text
200 OK
```

**Response Body:**

```json
{
  "id": 1,
  "name": "Premium Rose Bush",
  "unit": "each",
  "cost_per_unit": 6.99,
  "price_per_unit": 14.99,
  "quantity_in_stock": 15,
  "category_id": 1
}
```

## Failure: Invalid Numeric ID

If the identifier is numeric but less than or equal to zero:

**Status Code:**

```text
400 Bad Request
```

**Response Body:**

```json
{
  "detail": "Product ID must be greater than 0."
}
```

## Failure: Product Not Found

If no product matches the supplied ID or name:

**Status Code:**

```text
404 Not Found
```

**Response Body:**

```json
{
  "detail": "Product not found"
}
```

## Failure: Invalid Request Data

If a price or cost is zero or negative, or stock is negative, Pydantic rejects the request before the route calls the repository.

**Status Code:**

```text
422 Unprocessable Entity
```

The response contains a list explaining which field failed validation and why.

---

## Endpoint: Delete Product by ID

**Method:** `DELETE`

**Path:** `/products/{product_id}`

## Purpose

Permanently removes a product using its numeric ID.

## Request Body

None.

## Successful Response

**Status Code:**

```text
204 No Content
```

**Response Body:**

None.

A successful `204` response intentionally contains no JSON response body.

## Failure: Product Not Found

If the repository cannot find the product, it returns `False`.

The route checks the result and raises an `HTTPException`.

**Status Code:**

```text
404 Not Found
```

**Response Body:**

```json
{
  "detail": "Product with ID 999 was not found"
}
```

## Failure Flow

When a nonexistent product ID is deleted:

1. The client sends `DELETE /products/999`.
2. FastAPI matches the request to `delete_product_by_id`.
3. FastAPI converts the path value to an integer.
4. The `get_db` dependency creates a database session.
5. The route creates a `ProductRepository`.
6. The route calls `repository.delete_product_by_id(999)`.
7. The repository calls `get_product_by_id(999)`.
8. SQLAlchemy queries the product table.
9. No row is found, so the repository receives `None`.
10. The repository returns `False`.
11. The route detects the false result.
12. The route raises `HTTPException` with status code `404`.
13. FastAPI catches the `HTTPException`.
14. FastAPI converts it into a JSON HTTP response.
15. The client receives the `404 Not Found` response.
16. The `get_db` dependency closes the database session.

Because the missing product is handled intentionally, the request does not become an unhandled `500 Internal Server Error`.

---

## Endpoint: Delete Product by Name

**Method:** `DELETE`

**Path:** `/products/name/{product_name}`

## Purpose

Permanently deletes a product using its full name.

This route requires an exact product-name match before deletion.

## Example Request

```text
DELETE /products/name/Rose%20Bush
```

## Successful Response

**Status Code:**

```text
204 No Content
```

**Response Body:**

None.

## Failure: Partial Name Match

If the supplied name partially matches one product but is not the complete name:

**Status Code:**

```text
400 Bad Request
```

**Example Response:**

```json
{
  "detail": "'Rose' partially matches 'Rose Bush'. Enter the full product name to delete."
}
```

## Failure: Multiple Partial Matches

If the supplied name matches parts of multiple product names:

**Status Code:**

```text
400 Bad Request
```

**Example Response:**

```json
{
  "detail": "Multiple products match 'Rose': Rose Bush, Mini Rose Plant. Enter the full product name to delete."
}
```

## Failure: Product Not Found

If there is no exact or partial match:

**Status Code:**

```text
404 Not Found
```

**Example Response:**

```json
{
  "detail": "Product with name 'Unknown Product' was not found"
}
```

---

# Day 7: Category and Product Relationships

## Purpose

Day 7 introduces a one-to-many database relationship:

```text
One Category → Many Products
```

Examples of categories include:

* Seeds
* Tools
* Fertilizer
* Pottery
* Plants

Each product belongs to one category, while one category may contain several products.

---

# Database Models

## Category Model

The SQLAlchemy `Category` model contains:

```text
id
name
description
products
```

### Field Rules

* `id` is the primary key.
* `name` is required.
* `name` must be unique.
* `description` is optional.
* `products` represents the category's related products.

## Product Model

The SQLAlchemy `Product` model contains:

```text
id
name
unit
cost_per_unit
price_per_unit
quantity_in_stock
category_id
category
```

## Foreign Key

The foreign key is stored on the `Product` table:

```python
category_id = Column(
    Integer,
    ForeignKey("category.id", ondelete="SET NULL"),
    nullable=False,
    index=True,
)
```

The product is the child side of the relationship and owns the foreign key.

The category is the parent side.

## SQLAlchemy Relationship

The category model contains:

```python
products = relationship(
    "Product",
    back_populates="category",
    cascade="all, delete-orphan",
)
```

The product model contains:

```python
category = relationship(
    "Category",
    back_populates="products",
)
```

Together, these definitions allow SQLAlchemy to navigate the relationship in both directions:

```python
category.products
```

and:

```python
product.category
```

---

# Endpoint: Create Category

**Method:** `POST`

**Path:** `/categories`

## Purpose

Creates a category that products can later reference.

## Request Body

```json
{
  "name": "Plants",
  "description": "Indoor and outdoor living plants"
}
```

The description may be omitted or set to `null`.

Example:

```json
{
  "name": "Tools"
}
```

## Successful Response

**Status Code:**

```text
201 Created
```

**Response Body:**

```json
{
  "id": 1,
  "name": "Plants",
  "description": "Indoor and outdoor living plants",
  "products": []
}
```

## Failure: Duplicate Category Name

Because category names are unique, creating another category with the same name causes an `IntegrityError`.

The route catches the exception and rolls back the session.

**Status Code:**

```text
409 Conflict
```

**Response Body:**

```json
{
  "detail": "Category 'Plants' already exists"
}
```

---

# Endpoint: Get All Categories

**Method:** `GET`

**Path:** `/categories`

## Purpose

Returns all categories and the products associated with each category.

## Successful Response

**Status Code:**

```text
200 OK
```

**Response Body:**

```json
[
  {
    "id": 1,
    "name": "Plants",
    "description": "Indoor and outdoor living plants",
    "products": [
      {
        "id": 1,
        "name": "Rose Bush",
        "unit": "each",
        "cost_per_unit": 5.99,
        "price_per_unit": 12.99,
        "quantity_in_stock": 20,
        "category_id": 1
      }
    ]
  }
]
```

If no categories exist, the endpoint returns:

```json
[]
```

---

# Endpoint: Get Category With Products

**Method:** `GET`

**Path:** `/categories/{category_id}`

## Purpose

Returns one category along with its complete nested list of products.

## Example Request

```text
GET /categories/1
```

## Successful Response

**Status Code:**

```text
200 OK
```

**Response Body:**

```json
{
  "id": 1,
  "name": "Plants",
  "description": "Indoor and outdoor living plants",
  "products": [
    {
      "id": 1,
      "name": "Rose Bush",
      "unit": "each",
      "cost_per_unit": 5.99,
      "price_per_unit": 12.99,
      "quantity_in_stock": 20,
      "category_id": 1
    },
    {
      "id": 2,
      "name": "Fern",
      "unit": "each",
      "cost_per_unit": 4.5,
      "price_per_unit": 10.99,
      "quantity_in_stock": 12,
      "category_id": 1
    }
  ]
}
```

## Failure: Category Not Found

**Status Code:**

```text
404 Not Found
```

**Response Body:**

```json
{
  "detail": "Category with ID 999 was not found"
}
```

---

# Creating a Product With a Category

The existing `POST /products` endpoint accepts a `category_id`.

Before inserting the product, the route checks whether the category exists:

```python
if product_data.category_id is not None:
    cat_repo = CategoryRepository(db)

    if not cat_repo.get_category_by_id(product_data.category_id):
        raise HTTPException(...)
```

This provides a clear API error before the database insert occurs.

## Invalid Category Failure

**Status Code:**

```text
400 Bad Request
```

**Response Body:**

```json
{
  "detail": "Category with ID 999 does not exist"
}
```

---

# Foreign Key Constraint Responsibilities

The foreign key protects the database from storing a product whose category reference does not point to a real category.

In plain terms, it prevents a product from claiming that it belongs to a category that does not exist.

If PostgreSQL receives an insert such as:

```sql
INSERT INTO product (..., category_id)
VALUES (..., 999);
```

and category `999` does not exist, PostgreSQL rejects the insert with a foreign key violation.

Through SQLAlchemy, that database error normally surfaces as an `IntegrityError`.

Without error handling, the exception could reach FastAPI and result in:

```text
500 Internal Server Error
```

The current route avoids that problem by manually checking for the category before inserting the product and returning a controlled `400 Bad Request`.

The route also catches an `IntegrityError` during product creation and converts it into a `409 Conflict`. However, the message assumes that every integrity error means the product name is duplicated. Other database integrity failures could therefore receive a duplicate-name message even when another database constraint caused the failure.

---

# Pydantic Schema Responsibilities

## ProductSchema

`ProductSchema` validates product requests and controls product responses.

```python
class ProductSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    name: str
    unit: str
    cost_per_unit: float = Field(gt=0)
    price_per_unit: float = Field(gt=0)
    quantity_in_stock: float = Field(ge=0)
    category_id: int | None = None
```

`from_attributes=True` allows Pydantic to create responses from SQLAlchemy objects.

## CategoryCreate

`CategoryCreate` controls the request body used when creating a category.

```python
class CategoryCreate(BaseModel):
    name: str
    description: str | None = None
```

## CategorySchema

`CategorySchema` controls category responses and includes nested products.

```python
class CategorySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    products: list[ProductSchema] = []
```

This nested schema causes `GET /categories/{category_id}` to include the related products.

---

# Responsibility Separation

## Pydantic Responsibilities

Pydantic is responsible for:

* Checking that required request fields exist.
* Confirming that values use the expected data types.
* Rejecting costs and prices that are not greater than zero.
* Rejecting negative stock quantities.
* Converting SQLAlchemy model objects into API response data.
* Defining the public structure of API responses.

Pydantic validation occurs before the route performs database operations.

---

## SQLAlchemy Model Responsibilities

SQLAlchemy models are responsible for:

* Defining database table structures.
* Mapping Python objects to database rows.
* Defining primary keys.
* Defining unique constraints.
* Defining the category foreign key.
* Defining the Category-to-Product relationship.
* Managing persistence through the SQLAlchemy session.

---

## Repository Responsibilities

Repositories are responsible for direct database interactions.

### ProductRepository

The `ProductRepository` handles:

* Creating a product.
* Retrieving all products.
* Retrieving a product by ID.
* Retrieving a product by name.
* Filtering products.
* Deleting products by ID.
* Deleting products by name.

### ProductUpdateRepository

The `ProductUpdateRepository` handles:

* Finding a product by ID or name.
* Applying full product updates.
* Committing the update.
* Refreshing and returning the updated database object.

### CategoryRepository

The `CategoryRepository` handles:

* Creating categories.
* Retrieving all categories.
* Retrieving a category by ID.

Routes do not contain direct SQLAlchemy queries for the main product and category operations.

---

## FastAPI Route Responsibilities

Routes are responsible for:

* Receiving HTTP requests.
* Receiving validated Pydantic request objects.
* Receiving database sessions through `Depends(get_db)`.
* Calling repository methods.
* Checking repository results.
* Raising `HTTPException` for expected failures.
* Returning meaningful HTTP status codes.
* Declaring response models.
* Preventing known invalid category references before insertion.

---

## Database Session Responsibilities

The `get_db` dependency creates one SQLAlchemy session for each request.

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

This ensures that:

* Each request has access to a database session.
* Routes do not manually open sessions.
* The session closes after the request finishes.
* Session management remains consistent across endpoints.

---

# Response Model Decision

Every endpoint that returns product or category data uses `response_model`.

Examples:

```python
response_model=ProductSchema
```

```python
response_model=list[ProductSchema]
```

```python
response_model=CategorySchema
```

```python
response_model=list[CategorySchema]
```

Using response models ensures that:

* Only intended fields are returned.
* Responses follow a predictable API contract.
* SQLAlchemy objects are converted into serializable responses.
* Response data is validated before being sent.
* Swagger UI documents the response structure.
* Internal ORM implementation details are not automatically exposed.

Without `response_model`, FastAPI would attempt to serialize the returned SQLAlchemy object without enforcing the intended public response structure.

The route might still return data, but:

* The response would no longer be checked against `ProductSchema`.
* Fields could be added or removed accidentally.
* Internal fields could potentially be exposed.
* The documented API response would be less reliable.
* Changes to the SQLAlchemy model could unexpectedly change the API contract.

---

# HTTP Status Code Summary

| Endpoint                               | Successful Status |             Main Failure Statuses |
| -------------------------------------- | ----------------: | --------------------------------: |
| `POST /products`                       |     `201 Created` |               `400`, `409`, `422` |
| `GET /products`                        |          `200 OK` |                                 — |
| `GET /products/search/{identifier}`    |          `200 OK` |                             `404` |
| `GET /products/filter/`                |          `200 OK` | `422` for invalid parameter types |
| `PUT /products/{identifier}`           |          `200 OK` |               `400`, `404`, `422` |
| `DELETE /products/{product_id}`        |  `204 No Content` |                             `404` |
| `DELETE /products/name/{product_name}` |  `204 No Content` |                      `400`, `404` |
| `POST /categories`                     |     `201 Created` |                      `409`, `422` |
| `GET /categories`                      |          `200 OK` |                                 — |
| `GET /categories/{category_id}`        |          `200 OK` |                      `404`, `422` |

---

# Implementation Notes and Current Deviations

## 1. Category ID Is Optional in Pydantic but Required in SQLAlchemy

The Pydantic schema currently defines:

```python
category_id: int | None = None
```

The SQLAlchemy model defines:

```python
nullable=False
```

These rules conflict.

Pydantic allows a request without a category ID, but the database requires one. A request with no category ID may therefore pass Pydantic validation and fail during the database insert.

To require every product to have a category, the schema should use:

```python
category_id: int
```

---

## 2. ProductCreate Is Defined but Not Used

The code defines:

```python
class ProductCreate(BaseModel):
```

However, `POST /products` accepts:

```python
product_data: ProductSchema
```

A cleaner design would use:

```python
product_data: ProductCreate
```

after adding `category_id` to `ProductCreate`.

That would separate:

* Fields accepted from the client.
* Fields returned by the API.

---

## 3. Product Responses Do Not Include the Category Name

The Day 7 requirements ask for product responses to show something meaningful about the category, such as its name.

The current `ProductSchema` only returns:

```json
{
  "category_id": 1
}
```

It does not return:

```json
{
  "category": {
    "id": 1,
    "name": "Plants"
  }
}
```

The category endpoint satisfies the nested-response requirement because it returns a category with its products. However, an individual product response does not currently show its category name.

---

## 4. Product Update Does Not Change the Category

Although `ProductSchema` includes `category_id`, the update repository does not assign:

```python
product.category_id = product_data.category_id
```

Therefore, sending a different category ID in a `PUT` request does not move the product into another category.

---

## 5. Foreign Key Delete Behavior Has Conflicting Rules

The product foreign key uses:

```python
ondelete="SET NULL"
```

but the column also uses:

```python
nullable=False
```

`SET NULL` requires the database to be allowed to set `category_id` to `NULL`.

The category relationship also uses:

```python
cascade="all, delete-orphan"
```

which may cause SQLAlchemy to delete related products when the category is deleted.

These behaviors should be intentionally aligned before a category-delete endpoint is added.

---

## 6. Mutable Default List

The category schema uses:

```python
products: list[ProductSchema] = []
```

A safer Pydantic definition is:

```python
products: list[ProductSchema] = Field(default_factory=list)
```

This creates a new empty list for each schema instance.

---

# Definition of Done

The API satisfies the main requirements when the team can demonstrate:

* A category can be created.
* A product can be created using an existing category ID.
* A duplicate category returns `409`.
* A duplicate product returns `409`.
* An invalid category ID returns a controlled non-500 response.
* All products can be retrieved.
* One product can be retrieved by ID or name.
* Products can be filtered.
* Products can be updated.
* Invalid prices, costs, and stock values are rejected.
* Products can be deleted by ID.
* Products can be deleted by exact name.
* Missing products return `404`.
* Partial delete-by-name input returns `400`.
* A category can be retrieved with its products nested in the response.
* Response models remain on every endpoint that returns product or category data.
* The Postman collection includes successful and unsuccessful requests for each endpoint.
* The README documents the product and category endpoints.

August 5, 2026
Connect to Azure
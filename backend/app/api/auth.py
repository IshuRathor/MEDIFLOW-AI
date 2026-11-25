from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.security import (
    create_access_token,
    get_current_user,
    get_db,
    hash_password,
    verify_password
)
from app.models.user import User
from app.models.patient import Patient
from app.models.doctor import Doctor
from app.models.audit import AuditLog
from app.schemas.auth import (
    LoginRequest,
    PatientRegisterRequest,
    PublicRegisterRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    CreateUserRequest,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/registration-status")
def registration_status(db: Session = Depends(get_db)):
    return {"registration_allowed": db.query(User).count() == 0}


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_first_or_public(
    request: PublicRegisterRequest,
    db: Session = Depends(get_db),
):
    selected_role = request.role
    if selected_role is None:
        # Serialize the one-time bootstrap, including requests for different emails.
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            db.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
        elif dialect == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))

    email = str(request.email).strip().lower()
    if db.query(User).filter(User.email.ilike(email)).first():
        raise HTTPException(status_code=409, detail="Email is already registered")

    has_users = db.query(User.id).first() is not None
    if has_users and selected_role is None:
        raise HTTPException(status_code=400, detail="Select an account role")
    if not has_users and selected_role is not None:
        raise HTTPException(status_code=409, detail="Account registration opens after initial administrator setup")

    if selected_role is None:
        user = User(
            full_name=request.full_name.strip(),
            email=email,
            password_hash=hash_password(request.password),
            role="admin",
            is_active=True,
            approval_status="approved",
        )
        db.add(user)
    else:
        if request.role == "patient":
            user = User(
                full_name=request.full_name.strip(), email=email,
                password_hash=hash_password(request.password), role="patient",
                is_active=True, approval_status="approved",
            )
        else:
            user = User(
                full_name=request.full_name.strip(), email=email,
                password_hash=hash_password(request.password), role=request.role,
                is_active=False, approval_status="pending",
            )
        db.add(user)
        db.flush()

        if request.role == "patient":
            if db.query(Patient).filter(Patient.email.ilike(email)).first():
                db.rollback()
                raise HTTPException(status_code=409, detail="Email is already registered")
            db.add(Patient(
                name=request.full_name.strip(),
                phone=request.phone.strip(),
                email=email,
                user_id=user.id,
            ))
        elif request.role == "clinician":
            if db.query(Doctor).filter(Doctor.email.ilike(email)).first():
                db.rollback()
                raise HTTPException(status_code=409, detail="Email is already registered")
            db.add(Doctor(
                name=request.full_name.strip(),
                specialization=request.specialization,
                phone=request.phone.strip(),
                email=email,
                department=request.department,
                experience_years=request.experience_years,
                user_id=user.id,
            ))

    try:
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered") from error


@router.post(
    "/register-patient",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_patient_compatibility(
    request: PatientRegisterRequest,
    db: Session = Depends(get_db),
):
    return register_first_or_public(
        PublicRegisterRequest(
            full_name=request.full_name,
            email=request.email,
            phone=request.phone,
            password=request.password,
            confirm_password=request.confirm_password,
            role="patient",
        ),
        db,
    )


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.email == request.email,
    ).first()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    if getattr(user, "approval_status", "approved") != "approved" or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.approval_status}",
        )

    return TokenResponse(
        access_token=create_access_token(user),
        user=user
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    request: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create accounts",
        )
    if db.query(User).filter(User.email == request.email).first():
        raise HTTPException(status_code=409, detail="Email is already registered")

    patient = None
    if request.role == "patient":
        if request.patient_id is None:
            raise HTTPException(
                status_code=400,
                detail="patient_id is required for a patient account",
            )
        patient = db.query(Patient).filter(Patient.id == request.patient_id).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        if patient.user_id is not None:
            raise HTTPException(status_code=409, detail="Patient is already linked to an account")
        if patient.email and str(patient.email).lower() != str(request.email).lower():
            raise HTTPException(
                status_code=400,
                detail="Patient email must match the account email",
            )

    user = User(
        full_name=request.full_name,
        email=request.email,
        password_hash=hash_password(request.password),
        role=request.role,
    )
    db.add(user)
    db.flush()
    if patient:
        patient.user_id = user.id
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can view accounts",
        )
    return db.query(User).order_by(User.id).all()


@router.get("/pending-users", response_model=list[UserResponse])
def list_pending_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can view pending accounts")
    return db.query(User).filter(User.approval_status == "pending").order_by(User.id).all()


@router.post("/users/{user_id}/approve", response_model=UserResponse)
def approve_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can approve accounts")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")
    if user.approval_status != "pending":
        raise HTTPException(status_code=409, detail="Account is not pending")
    user.approval_status = "approved"
    user.is_active = True
    db.add(AuditLog(
        actor_user_id=current_user.id,
        action="APPROVE_REGISTRATION",
        resource="user",
        resource_id=str(user.id),
        method="POST",
        path=f"/api/auth/users/{user.id}/approve",
        status_code=200,
        metadata_json={"email": user.email, "role": user.role},
    ))
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/reject", response_model=UserResponse)
def reject_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can reject accounts")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")
    if user.approval_status != "pending":
        raise HTTPException(status_code=409, detail="Account is not pending")
    user.approval_status = "rejected"
    user.is_active = False
    db.add(AuditLog(
        actor_user_id=current_user.id,
        action="REJECT_REGISTRATION",
        resource="user",
        resource_id=str(user.id),
        method="POST",
        path=f"/api/auth/users/{user.id}/reject",
        status_code=200,
        metadata_json={"email": user.email, "role": user.role},
    ))
    db.commit()
    db.refresh(user)
    return user


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(current_user: User = Depends(get_current_user)):
    return TokenResponse(
        access_token=create_access_token(current_user),
        user=current_user,
    )

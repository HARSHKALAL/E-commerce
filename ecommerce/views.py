from django.shortcuts import render,redirect
from .forms import Userform,EditProfileForm
from django.contrib.auth.forms import AuthenticationForm,PasswordChangeForm
from django.contrib.auth import authenticate,login,logout,update_session_auth_hash
from django.http import HttpResponseRedirect,HttpResponse,JsonResponse
from .models import User,Category,Product,MerchantFirm,Carousel,Cart,Order
import json
from django.db.models import Sum,F,DecimalField,ExpressionWrapper,Value
from .utils import *
from django.core.serializers.json import DjangoJSONEncoder
import stripe
from django.views.decorators.csrf import csrf_exempt

def homepage(request):  
    category_name = request.GET.get('cat')    
    categories=Category.objects.filter(is_deleted=False) 
    carousel_image=Carousel.objects.order_by('image')[0:3]
    cart_count=Cart.objects.filter(user_id=request.user.id).aggregate(Sum('quantity'))

    if category_name:
        categories=categories.filter(name__icontains=category_name)
    return render(request,"enroll/homepage.html",{'categories':categories,"carousel_image":carousel_image,"cart_count":cart_count})

def signup(request):
    form=Userform()
    if request.method == "POST":
        form=Userform(request.POST,request.FILES)
        if form.is_valid():
            print(form)
            form.save()  
            form=Userform()
    else:
        form=Userform()
    return render(request,"enroll/register.html",{'form':form})

def signin(request):
    if request.method == "POST":
        a=sign_in(request,request.POST)
        if a.get('status') == 201:
            return HttpResponseRedirect("/homepage/")       
    loginform=AuthenticationForm()
    return render(request,'enroll/login.html',{'loginform':loginform})

def user_logout(request):
    logout(request)
    return HttpResponseRedirect('/signin/')

def changepassword(request):
    if request.method == "POST":
        change_pass=PasswordChangeForm(data=request.POST,user=request.user)
        if change_pass.is_valid():
            change_pass.save()
            return HttpResponseRedirect('/homepage/')
    else:
        change_pass=PasswordChangeForm(user=request.user)
    return render(request,'enroll/changepassword.html',{'change_pass':change_pass})

def editprofile(request):
    if request.method == 'POST':
        edit_form=EditProfileForm(request.POST,request.FILES,instance=request.user)
        if edit_form.is_valid():  
            edit_form.save()  
            return HttpResponseRedirect("/homepage/")  
        else:
            print(edit_form.errors)
    else:
        edit_form=EditProfileForm(instance=request.user)
    return render(request,'enroll/editprofile.html',{'edit_form':edit_form})

def product(request,id):
    product=Product.objects.get(id=id)
    return render(request,'enroll/product.html',{'product':product})
    
def addproduct(request):
    solds_by=MerchantFirm.objects.all()
    category=Category.objects.all()
    if request.method == "POST":
        add_product_data(request.POST,request.FILES,Product)
    return render(request,"enroll/addproduct.html",{'solds_by':solds_by,'category':category})

def update_product(request,id):
    solds_by=MerchantFirm.objects.all()
    category=Category.objects.all()    
    product_data=Product.objects.get(id=id)
    if request.method == 'POST':
        updateproduct(request.POST,request.FILES,Product,id)      
    return render(request,"enroll/update_product.html",{'solds_by':solds_by,'category':category,'product_data':product_data})

def delete_product(request,id):    
    delete_product=Product.objects.get(id=id).delete()
    return HttpResponseRedirect("/homepage/")

def remove_category(request,id,p_id):
    product=Product.objects.get(id=p_id)
    product.category.remove(id)    
    return HttpResponse("Deleted")

def remove_sold_by(request,id,p_id):
    product=Product.objects.get(id=p_id)
    product.sold_by.remove(id)    
    return HttpResponse("Deleted")

def cart_product(request,id):
    cart=Cart.objects.get_or_create(user_id=request.user.id,product_id=id)
    return HttpResponse("Created Successfully")

def view_cart(request):
    cart_view=Cart.objects.filter(user=request.user.id)
    cart_total_final = Cart.objects.filter(user_id=request.user.id).annotate(sum_total = ExpressionWrapper(F('product__price') * F('quantity'), output_field=DecimalField()))
    final_show = cart_total_final.values("sum_total").annotate(totals=Sum("sum_total"))
    new_try = final_show.aggregate(total=Sum('totals'))
      
    return render(request,"enroll/cart.html",{'cart_view':cart_view,"total":new_try.get('total')})

def remove_cart_Product(request,id):
    cart_product=Cart.objects.get(id=id).delete()    
    return HttpResponse("Delete")

def update_cart_Product(request,id):
    if request.method == 'POST':
        add=request.POST['add']
        cart_total_final = Cart.objects.filter(user_id=request.user.id).annotate(sum_total = ExpressionWrapper(F('product__price') * F('quantity'), output_field=DecimalField()))
        final_show = cart_total_final.values("sum_total").annotate(totals=Sum("sum_total"))
        new_try = final_show.aggregate(total=Sum('totals'))        
        
        cart_product=Cart.objects.get(product_id=id,user_id = request.user.id)                      
        if  cart_product.product.stock_quantity <= cart_product.quantity :                        
            return HttpResponse("not available")
        else:
            if add == 'add':
                cart_product.quantity = cart_product.quantity + 1    
                cart_product.save()
                return JsonResponse({"msg":"added in cart","qty":cart_product.quantity,"price":cart_product.product.price,"total":new_try.get('total')})
            else:
                if cart_product.quantity == 1:
                    cart_product.delete()
                    return JsonResponse({"msg":"not in stock","price":cart_product.product.price,"total":new_try.get('total')})
                else:
 
                    cart_product.quantity = cart_product.quantity - 1    
                    cart_product.save()
                    return JsonResponse({"msg":"removed from cart","qty":cart_product.quantity,"price":cart_product.product.price,"total":new_try.get('total')})

def confirm_order(request):
    total=request.POST['totalamount']
    total_updated = json.loads(total)
        
    order_confirmation=Cart.objects.filter(user_id=request.user.id)
    order_data=order_confirmation.values('product_id','product__price','product__stock_quantity','quantity')

    data_json = list(order_data)

    orders=[]
    for order in  order_confirmation:
        data={"product_id":order.product.id,"price":str(order.product.price),"quantity":order.quantity}
        orders.append({"data":data,"stock_quntity":order.product.stock_quantity})
    
    order_confirm=Order.objects.create(user_id=request.user.id,total_amount=total_updated,order_details=json.loads(json.dumps(data_json,cls=DecimalEncoder)))
    order_confirm.save()
    
    total_stock_quantity(order_data)

    return JsonResponse({"id":order_confirm.id,"order":order_confirm.order_details})

def my_orders(request):
    my_order=Order.objects.filter(user_id=request.user.id)
    order_data=list(my_order.values('order_details'))
    return render(request,"enroll/my_orders.html",{'my_order':my_order,"product_details":order_json_to_products(order_data)})

# @csrf_exempt
# def create_checkout_session(request):
#     booking_id = request.GET.get('id')
#     user_booking = Order.objects.get(id=booking_id)
#     session = stripe.checkout.Session.create(
#     payment_method_types=['card'],
#     line_items=[{
#     'price_data':  {
#     'currency': 'inr',
#     'product_data': {
#     'name': str(user_booking.show_movie.movie.title),
#     },
#     'unit_amount': int((user_booking.show_movie.seat_price)*100),
#     },
#     'quantity': int(user_booking.booked_seats),
#     }],
#     mode='payment',
#     success_url=YOUR_DOMAIN + '/success.html',
#     cancel_url=YOUR_DOMAIN + '/cancel.html',
#     )
#     return JsonResponse({'id': session.id})

# @csrf_exempt
# def webhook(request):
#     endpoint_secret = ''
#     payload = request.body
#     print(payload,'payload')
#     sig_header = request.META['HTTP_STRIPE_SIGNATURE']
#     event = None

#     try:
#         event = stripe.Webhook.construct_event(
#         payload, sig_header, endpoint_secret
#         )
#     except ValueError as e:
#         return HttpResponse(status=400)
    
#     except stripe.error.SignatureVerificationError as e:
#         return HttpResponse(status=400)

#     if event['type'] == 'checkout.session.completed':
#         print("Payment was successful.")
#         return HttpResponse(status=200)

